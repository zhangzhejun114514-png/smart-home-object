"""
Home Assistant 硬件接口层（稳定增强版）
===========================
通过 Home Assistant REST API 连接香橙派上的真实硬件设备。
增强特性：指数退避重试、连接健康追踪、绝对路径配置
"""

import requests
import json
import threading
import time
import logging
import os
from datetime import datetime
from utils import retry_with_backoff, ConnectionHealth

logger = logging.getLogger(__name__)

# 配置文件绝对路径（避免 CWD 变化导致找不到文件）
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ha_config.json')


class HomeAssistantClient:
    """Home Assistant REST API 客户端（稳定增强版）"""

    def __init__(self, config_path=None):
        self.config_path = config_path or CONFIG_PATH
        self.config = self._load_config(self.config_path)
        self.base_url = self.config.get('ha_url', 'http://localhost:8123')
        self.token = self.config.get('ha_token', '')
        self.connected = False
        self.entities = {}
        self._sync_thread = None
        self._callbacks = []
        # 连接健康状态管理器
        self.health = ConnectionHealth("HomeAssistant")
        # 线程锁保护配置读写
        self._config_lock = threading.Lock()

    def _load_config(self, path):
        """加载HA连接配置（绝对路径）"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"HA config not found at {path}, using defaults")
            return {
                'ha_url': 'http://localhost:8123',
                'ha_token': '',
                'device_mapping': {
                    'temperature_sensor': 'sensor.indoor_temperature',
                    'humidity_sensor': 'sensor.indoor_humidity',
                    'front_door': 'binary_sensor.front_door',
                    'living_window': 'binary_sensor.living_room_window',
                    'main_light': 'light.living_room',
                    'fan': 'fan.smart_fan',
                    'ac': 'climate.smart_ac',
                    'door_lock': 'lock.front_door',
                    'camera': 'camera.security_camera',
                },
                'poll_interval': 10
            }

    def _headers(self):
        """请求头"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    # ==================== 连接管理（带重试） ====================

    @retry_with_backoff(max_retries=2, base_delay=0.5, max_delay=4.0,
                        exceptions=(requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout))
    def test_connection(self):
        """测试与HA的连接（带重试）"""
        try:
            resp = requests.get(
                f'{self.base_url}/api/',
                headers=self._headers(),
                timeout=(3, 5)  # (connect_timeout, read_timeout)
            )
            if resp.status_code == 200:
                self.connected = True
                self.health.record_success()
                return {'connected': True, 'message': resp.json().get('message', 'API running')}
            self.connected = False
            self.health.record_failure(f'HTTP {resp.status_code}')
            return {'connected': False, 'message': f'HTTP {resp.status_code}'}
        except requests.exceptions.ConnectionError as e:
            self.connected = False
            self.health.record_failure(str(e))
            return {'connected': False, 'message': '无法连接到 Home Assistant，请检查地址和端口'}
        except requests.exceptions.Timeout as e:
            self.connected = False
            self.health.record_failure('timeout')
            return {'connected': False, 'message': '连接超时，HA 响应过慢'}
        except Exception as e:
            self.connected = False
            self.health.record_failure(str(e))
            return {'connected': False, 'message': str(e)}

    @retry_with_backoff(max_retries=1, base_delay=0.5, max_delay=2.0,
                        exceptions=(requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout))
    def get_config(self):
        """获取HA配置信息（带重试）"""
        try:
            resp = requests.get(
                f'{self.base_url}/api/config',
                headers=self._headers(),
                timeout=(3, 8)
            )
            if resp.status_code == 200:
                self.health.record_success()
                data = resp.json()
                return {
                    'version': data.get('version'),
                    'location': data.get('location_name'),
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'timezone': data.get('time_zone'),
                    'unit_system': data.get('unit_system'),
                }
        except Exception as e:
            logger.error(f'获取HA配置失败: {e}')
            self.health.record_failure(str(e))
        return None

    def save_config(self, ha_url, ha_token, device_mapping=None):
        """保存HA连接配置（绝对路径 + 线程安全）"""
        with self._config_lock:
            self.config['ha_url'] = ha_url
            self.config['ha_token'] = ha_token
            if device_mapping:
                self.config['device_mapping'] = device_mapping
            self.base_url = ha_url
            self.token = ha_token

            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                logger.info(f"HA config saved to {self.config_path}")
                return True
            except Exception as e:
                logger.error(f"保存HA配置失败: {e}")
                return False

    def get_health_status(self):
        """获取连接健康状态"""
        status = self.health.get_status()
        status['ha_url'] = self.base_url
        status['connected'] = self.connected
        return status

    # ==================== 实体状态（带重试） ====================

    @retry_with_backoff(max_retries=2, base_delay=0.3, max_delay=3.0,
                        exceptions=(requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout))
    def get_all_states(self):
        """获取所有实体状态（带重试）"""
        try:
            resp = requests.get(
                f'{self.base_url}/api/states',
                headers=self._headers(),
                timeout=(3, 15)
            )
            if resp.status_code == 200:
                states = resp.json()
                self.entities = {s['entity_id']: s for s in states}
                self.health.record_success()
                return self.entities
        except Exception as e:
            logger.error(f'获取状态失败: {e}')
            self.health.record_failure(str(e))
        return {}

    @retry_with_backoff(max_retries=1, base_delay=0.3, max_delay=2.0,
                        exceptions=(requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout))
    def get_entity(self, entity_id):
        """获取单个实体状态（带重试）"""
        try:
            resp = requests.get(
                f'{self.base_url}/api/states/{entity_id}',
                headers=self._headers(),
                timeout=(3, 5)
            )
            if resp.status_code == 200:
                self.health.record_success()
                return resp.json()
            return None
        except Exception as e:
            logger.error(f'获取实体 {entity_id} 失败: {e}')
            self.health.record_failure(str(e))
            return None

    def set_entity_state(self, entity_id, state, attributes=None):
        """设置实体状态（虚拟实体）"""
        try:
            data = {'state': state}
            if attributes:
                data['attributes'] = attributes
            resp = requests.post(
                f'{self.base_url}/api/states/{entity_id}',
                headers=self._headers(), json=data, timeout=(3, 5)
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f'设置实体 {entity_id} 状态失败: {e}')
            return False

    # ==================== 服务调用（带重试） ====================

    @retry_with_backoff(max_retries=2, base_delay=0.5, max_delay=4.0,
                        exceptions=(requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout))
    def call_service(self, domain, service, entity_id, service_data=None):
        """调用HA服务（控制设备，带重试）"""
        try:
            data = {'entity_id': entity_id}
            if service_data:
                data.update(service_data)
            resp = requests.post(
                f'{self.base_url}/api/services/{domain}/{service}',
                headers=self._headers(), json=data, timeout=(3, 12)
            )
            if resp.status_code == 200:
                self.health.record_success()
                return {'success': True, 'changed_states': resp.json()}
            return {'success': False, 'status': resp.status_code}
        except Exception as e:
            logger.error(f'调用服务 {domain}.{service} 失败: {e}')
            self.health.record_failure(str(e))
            return {'success': False, 'message': str(e)}

    # ==================== 便捷设备控制方法 ====================

    def get_temperature(self):
        """获取温度传感器数据"""
        eid = self.config['device_mapping'].get('temperature_sensor')
        if eid:
            state = self.get_entity(eid)
            if state:
                try:
                    return float(state.get('state', 0))
                except (ValueError, TypeError):
                    return None
        return None

    def get_humidity(self):
        """获取湿度传感器数据"""
        eid = self.config['device_mapping'].get('humidity_sensor')
        if eid:
            state = self.get_entity(eid)
            if state:
                try:
                    return float(state.get('state', 0))
                except (ValueError, TypeError):
                    return None
        return None

    def control_light(self, action, brightness=None):
        """控制灯光 (on/off/toggle)"""
        eid = self.config['device_mapping'].get('main_light')
        service_data = {}
        if action == 'on' and brightness is not None:
            service_data['brightness_pct'] = brightness
        return self.call_service('light', action, eid, service_data if service_data else None)

    def control_fan(self, speed_pct=None):
        """控制风扇"""
        eid = self.config['device_mapping'].get('fan')
        if speed_pct is not None and speed_pct > 0:
            return self.call_service('fan', 'turn_on', eid, {'percentage': speed_pct})
        else:
            return self.call_service('fan', 'turn_off', eid)

    def control_ac(self, mode='off', temperature=None):
        """控制空调"""
        eid = self.config['device_mapping'].get('ac')
        if mode == 'off':
            return self.call_service('climate', 'turn_off', eid)
        else:
            service_data = {'hvac_mode': mode}
            if temperature:
                service_data['temperature'] = temperature
            return self.call_service('climate', 'set_temperature', eid, service_data)

    def control_door(self, action='unlock'):
        """控制门锁"""
        eid = self.config['device_mapping'].get('door_lock')
        return self.call_service('lock', action, eid)

    def get_door_status(self):
        """获取门状态"""
        eid = self.config['device_mapping'].get('front_door')
        state = self.get_entity(eid)
        if state:
            return state.get('state', 'off')
        return None

    def get_window_status(self):
        """获取窗户状态"""
        eid = self.config['device_mapping'].get('living_window')
        state = self.get_entity(eid)
        if state:
            return state.get('state', 'off')
        return None

    def get_camera_image(self):
        """获取摄像头图像"""
        eid = self.config['device_mapping'].get('camera')
        if not eid:
            return None
        try:
            resp = requests.get(
                f'{self.base_url}/api/camera_proxy/{eid}',
                headers=self._headers(), timeout=(3, 10)
            )
            if resp.status_code == 200 and 'image' in resp.headers.get('content-type', ''):
                return resp.content
        except Exception as e:
            logger.error(f'获取摄像头图像失败: {e}')
        return None

    # ==================== 设备映射 ====================

    def get_device_mapping(self):
        """获取设备映射配置"""
        return self.config.get('device_mapping', {})

    def update_device_mapping(self, device_type, entity_id):
        """更新设备映射"""
        self.config['device_mapping'][device_type] = entity_id
        return self.save_config(self.config['ha_url'], self.config['ha_token'], self.config['device_mapping'])

    def get_discovered_devices(self):
        """获取HA中所有已发现的设备"""
        try:
            states = self.get_all_states()
            devices = []
            for eid, state in states.items():
                attrs = state.get('attributes', {})
                devices.append({
                    'entity_id': eid,
                    'state': state.get('state'),
                    'friendly_name': attrs.get('friendly_name', eid),
                    'domain': eid.split('.')[0],
                    'last_changed': state.get('last_changed'),
                })
            return sorted(devices, key=lambda x: x['friendly_name'])
        except Exception as e:
            logger.error(f'获取设备列表失败: {e}')
            return []

    # ==================== 历史数据 ====================

    def get_history(self, entity_ids, start_time=None):
        """获取HA历史数据"""
        try:
            url = f'{self.base_url}/api/history/period'
            params = {'filter_entity_id': ','.join(entity_ids), 'minimal_response': ''}
            if start_time:
                params['start'] = start_time
            resp = requests.get(url, headers=self._headers(), params=params, timeout=(3, 20))
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f'获取HA历史数据失败: {e}')
        return []


# 全局HA客户端实例
ha_client = HomeAssistantClient()
