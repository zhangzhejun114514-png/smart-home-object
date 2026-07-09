import sqlite3
import json
from datetime import datetime, timedelta
import random
import threading
import time
import logging

logger = logging.getLogger(__name__)

class SmartHomeDB:
    def __init__(self, db_path='smart_home.db'):
        self.db_path = db_path
        self._init_lock = threading.Lock()
        self._conn_lock = threading.Lock()
        with self._init_lock:
            self.init_database()
        self._start_simulation()

    def get_connection(self):
        """获取数据库连接（线程安全）"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """初始化数据库（带异常恢复）"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 温度历史数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS temperature_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    temperature REAL NOT NULL,
                    humidity REAL DEFAULT 50.0
                )
            ''')

            # 门窗状态历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS door_window_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    device_type TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            ''')

            # 灯光控制历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS light_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    light_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    brightness INTEGER DEFAULT 0
                )
            ''')

            # 门禁记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    person_name TEXT NOT NULL,
                    access_type TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            ''')

            # 授权人员表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS authorized_persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    rfid_tag TEXT,
                    face_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 系统状态表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    temperature REAL DEFAULT 25.0,
                    humidity REAL DEFAULT 50.0,
                    fan_speed INTEGER DEFAULT 0,
                    ac_status TEXT DEFAULT 'off',
                    ac_temperature INTEGER DEFAULT 26,
                    door_status TEXT DEFAULT 'closed',
                    window_status TEXT DEFAULT 'closed',
                    light_status TEXT DEFAULT 'off',
                    light_brightness INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 初始化系统状态
            cursor.execute('''
                INSERT OR IGNORE INTO system_status (id) VALUES (1)
            ''')

            # 人脸识别事件表（香橙派推送的识别结果）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS face_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    face_id TEXT,
                    person_name TEXT,
                    confidence REAL,
                    image_path TEXT,
                    device_source TEXT DEFAULT 'orange_pi',
                    status TEXT DEFAULT 'pending',
                    verified BOOLEAN DEFAULT 0
                )
            ''')

            # 插入默认授权人员（含人脸ID）
            cursor.execute('''
                INSERT OR IGNORE INTO authorized_persons (name, rfid_tag, face_id) VALUES
                ('\u7ba1\u7406\u5458', 'RFID001', 'FACE001'),
                ('\u5bb6\u5ead\u6210\u5458A', 'RFID002', 'FACE002'),
                ('\u5bb6\u5ead\u6210\u5458B', 'RFID003', 'FACE003')
            ''')

            conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database init error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def _start_simulation(self):
        """启动背景数据模拟线程"""
        def simulate():
            while True:
                try:
                    self._simulate_temperature()
                    time.sleep(120)  # 每2分钟模拟一次数据
                except Exception as e:
                    logger.error(f"Simulation error: {e}")
                    time.sleep(120)

        thread = threading.Thread(target=simulate, daemon=True)
        thread.start()

    def _simulate_temperature(self):
        """模拟温度数据变化"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 获取当前状态
            cursor.execute('SELECT temperature, fan_speed FROM system_status WHERE id = 1')
            row = cursor.fetchone()
            current_temp = row['temperature'] if row else 25.0
            fan_speed = row['fan_speed'] if row else 0

            # 模拟温度变化（随机波动）
            new_temp = current_temp + random.uniform(-0.5, 0.8)
            if fan_speed > 0:
                new_temp -= fan_speed * 0.1  # 风扇降温效果
            new_temp = max(18.0, min(35.0, new_temp))  # 限制在18-35度之间

            # 更新系统状态
            cursor.execute('''
                UPDATE system_status
                SET temperature = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (new_temp,))

            # 记录历史数据
            humidity = random.uniform(40.0, 70.0)
            cursor.execute('''
                INSERT INTO temperature_history (temperature, humidity) VALUES (?, ?)
            ''', (new_temp, humidity))

            conn.commit()
        except Exception as e:
            logger.error(f"Temperature simulation error: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_current_status(self):
        """获取当前系统状态"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM system_status WHERE id = 1')
            row = cursor.fetchone()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Get status error: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def update_status(self, **kwargs):
        """更新系统状态"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            allowed_fields = ['temperature', 'humidity', 'fan_speed', 'ac_status',
                             'ac_temperature', 'door_status', 'window_status',
                             'light_status', 'light_brightness']

            updates = []
            values = []
            for key, value in kwargs.items():
                if key in allowed_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)

            if updates:
                updates.append("last_updated = CURRENT_TIMESTAMP")
                query = f"UPDATE system_status SET {', '.join(updates)} WHERE id = 1"
                cursor.execute(query, values)
                conn.commit()

            return self.get_current_status()
        except Exception as e:
            logger.error(f"Update status error: {e}")
            if conn:
                conn.rollback()
            return {}
        finally:
            if conn:
                conn.close()

    def get_temperature_history(self, hours=24):
        """获取温度历史数据"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            since = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT timestamp, temperature, humidity
                FROM temperature_history
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            ''', (since,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get temperature history error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_door_window_history(self, hours=24):
        """获取门窗状态历史"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            since = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT timestamp, device_type, device_name, status
                FROM door_window_history
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            ''', (since,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get door/window history error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_door_window_event(self, device_type, device_name, status):
        """添加门窗状态变更记录"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO door_window_history (device_type, device_name, status)
                VALUES (?, ?, ?)
            ''', (device_type, device_name, status))
            conn.commit()
        except Exception as e:
            logger.error(f"Add door/window event error: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_light_history(self, hours=24):
        """获取灯光控制历史"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            since = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT timestamp, light_name, status, brightness
                FROM light_history
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            ''', (since,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get light history error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_light_event(self, light_name, status, brightness):
        """添加灯光控制记录"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO light_history (light_name, status, brightness)
                VALUES (?, ?, ?)
            ''', (light_name, status, brightness))
            conn.commit()
        except Exception as e:
            logger.error(f"Add light event error: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_access_logs(self, limit=50):
        """获取门禁记录"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM access_logs
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get access logs error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_access_log(self, person_name, access_type, status):
        """添加门禁记录"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO access_logs (person_name, access_type, status)
                VALUES (?, ?, ?)
            ''', (person_name, access_type, status))
            conn.commit()
        except Exception as e:
            logger.error(f"Add access log error: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_authorized_persons(self):
        """获取授权人员列表"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM authorized_persons')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get authorized persons error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_authorized_person(self, name, rfid_tag=None, face_id=None):
        """添加授权人员"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO authorized_persons (name, rfid_tag, face_id)
                VALUES (?, ?, ?)
            ''', (name, rfid_tag, face_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Add authorized person error: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def get_statistics(self):
        """获取统计数据"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            stats = {}

            # 平均温度（最近24小时）
            cursor.execute('''
                SELECT AVG(temperature) as avg_temp,
                       MAX(temperature) as max_temp,
                       MIN(temperature) as min_temp,
                       AVG(humidity) as avg_humidity
                FROM temperature_history
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            row = cursor.fetchone()
            stats['temperature_24h'] = {
                'avg': round(row['avg_temp'], 2) if row['avg_temp'] else None,
                'max': round(row['max_temp'], 2) if row['max_temp'] else None,
                'min': round(row['min_temp'], 2) if row['min_temp'] else None,
                'avg_humidity': round(row['avg_humidity'], 2) if row['avg_humidity'] else None
            }

            # 门禁统计
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status = 'granted' THEN 1 ELSE 0 END) as granted,
                       SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END) as denied
                FROM access_logs
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            row = cursor.fetchone()
            stats['access_24h'] = {
                'total': row['total'] or 0,
                'granted': row['granted'] or 0,
                'denied': row['denied'] or 0
            }

            # 灯光使用统计
            cursor.execute('''
                SELECT COUNT(*) as total_changes,
                       SUM(CASE WHEN status = 'on' THEN 1 ELSE 0 END) as on_count
                FROM light_history
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            row = cursor.fetchone()
            stats['light_24h'] = {
                'total_changes': row['total_changes'] or 0,
                'on_count': row['on_count'] or 0
            }

            return stats
        except Exception as e:
            logger.error(f"Get statistics error: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    # ==================== 人脸识别事件 ====================

    def add_face_event(self, face_id, person_name=None, confidence=None, image_path=None, device_source='orange_pi'):
        """添加人脸识别事件（由香橙派推送）"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO face_events (face_id, person_name, confidence, image_path, device_source)
                VALUES (?, ?, ?, ?, ?)
            ''', (face_id, person_name, confidence, image_path, device_source))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Add face event error: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_face_events(self, limit=20):
        """获取人脸识别事件列表"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM face_events
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get face events error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_latest_face_event(self):
        """获取最新的人脸识别事件"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM face_events
                ORDER BY timestamp DESC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Get latest face event error: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_face_event_status(self, event_id, status, verified=False):
        """更新人脸识别事件状态"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE face_events
                SET status = ?, verified = ?
                WHERE id = ?
            ''', (status, verified, event_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Update face event error: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


# 全局数据库实例
db = SmartHomeDB()
