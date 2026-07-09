from flask import Flask, render_template, jsonify, request
from database import db
from datetime import datetime
from ha_client import ha_client
from face_recognition import face_engine
from utils import api_error_handler, safe_base64_decode

app = Flask(__name__)

# ==================== 全局异常处理 ====================
# 捕获所有未处理异常，防止 Flask 返回 500 错误页面导致前端卡死

@app.errorhandler(Exception)
def handle_global_error(e):
    import traceback
    app.logger.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
    return jsonify({
        'error': '服务器内部错误',
        'error_en': 'Internal server error',
        'detail': str(e) if app.debug else None
    }), 500

@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({
        'error': '接口不存在',
        'error_en': 'API endpoint not found'
    }), 404

# ==================== 页面路由 ====================

@app.route('/')
def index():
    """主仪表盘页面"""
    return render_template('dashboard.html')

@app.route('/history')
def history_page():
    """历史数据页面"""
    return render_template('history.html')

@app.route('/access')
def access_page():
    """门禁管理页面"""
    return render_template('access.html')

@app.route('/hardware')
def hardware_page():
    """硬件管理页面"""
    return render_template('hardware.html')

# ==================== API: 系统状态 ====================

@app.route('/api/status')
def get_status():
    """获取当前系统所有状态"""
    status = db.get_current_status()
    # 补充统计信息
    stats = db.get_statistics()
    status['statistics'] = stats
    return jsonify(status)

# ==================== API: 温度 ====================

@app.route('/api/temperature', methods=['GET'])
def get_temperature():
    """获取温度历史"""
    hours = request.args.get('hours', 24, type=int)
    data = db.get_temperature_history(hours)
    return jsonify(data)

@app.route('/api/temperature/stats', methods=['GET'])
def get_temperature_stats():
    """获取温度统计"""
    stats = db.get_statistics()
    return jsonify(stats.get('temperature_24h', {}))

# ==================== API: 门窗控制 ====================

@app.route('/api/door', methods=['GET'])
def get_door_status():
    """获取门状态"""
    status = db.get_current_status()
    return jsonify({'door_status': status.get('door_status', 'closed')})

@app.route('/api/door', methods=['POST'])
def control_door():
    """控制门开关"""
    data = request.json
    new_status = data.get('status', 'closed')
    if new_status not in ('open', 'closed'):
        return jsonify({'error': '无效状态，只能是 open 或 closed'}), 400
    db.update_status(door_status=new_status)
    db.add_door_window_event('door', '前门', new_status)
    action = 'opened' if new_status == 'open' else 'closed'
    return jsonify({'door_status': new_status, 'message': f'门已{"打开" if new_status == "open" else "关闭"}', 'message_en': f'Door {action}'})

@app.route('/api/window', methods=['GET'])
def get_window_status():
    """获取窗户状态"""
    status = db.get_current_status()
    return jsonify({'window_status': status.get('window_status', 'closed')})

@app.route('/api/window', methods=['POST'])
def control_window():
    """控制窗户开关"""
    data = request.json
    new_status = data.get('status', 'closed')
    if new_status not in ('open', 'closed'):
        return jsonify({'error': '无效状态'}), 400
    db.update_status(window_status=new_status)
    db.add_door_window_event('window', '客厅窗户', new_status)
    action = 'opened' if new_status == 'open' else 'closed'
    return jsonify({'window_status': new_status, 'message': f'窗户已{"打开" if new_status == "open" else "关闭"}', 'message_en': f'Window {action}'})

@app.route('/api/door_window/history', methods=['GET'])
def get_door_window_history():
    """获取门窗历史"""
    hours = request.args.get('hours', 24, type=int)
    data = db.get_door_window_history(hours)
    return jsonify(data)

# ==================== API: 灯光控制 ====================

@app.route('/api/light', methods=['GET'])
def get_light_status():
    """获取灯光状态"""
    status = db.get_current_status()
    return jsonify({
        'light_status': status.get('light_status', 'off'),
        'light_brightness': status.get('light_brightness', 0)
    })

@app.route('/api/light', methods=['POST'])
def control_light():
    """控制灯光开关和亮度"""
    data = request.json
    light_status = data.get('status', 'off')
    brightness = data.get('brightness', 0)
    
    db.update_status(light_status=light_status, light_brightness=brightness)
    db.add_light_event('客厅主灯', light_status, brightness)
    
    return jsonify({
        'light_status': light_status,
        'light_brightness': brightness,
        'message': f'灯光已{"打开" if light_status == "on" else "关闭"}，亮度: {brightness}%',
        'message_en': f'Light {"turned on" if light_status == "on" else "turned off"}, brightness: {brightness}%'
    })

@app.route('/api/light/history', methods=['GET'])
def get_light_history():
    """获取灯光历史"""
    hours = request.args.get('hours', 24, type=int)
    data = db.get_light_history(hours)
    return jsonify(data)

# ==================== API: 风扇 ====================

@app.route('/api/fan', methods=['GET'])
def get_fan_status():
    """获取风扇状态"""
    status = db.get_current_status()
    return jsonify({'fan_speed': status.get('fan_speed', 0)})

@app.route('/api/fan', methods=['POST'])
def control_fan():
    """控制风扇速度"""
    data = request.json
    fan_speed = data.get('speed', 0)
    fan_speed = max(0, min(100, fan_speed))
    db.update_status(fan_speed=fan_speed)
    return jsonify({'fan_speed': fan_speed, 'message': f'风扇速度已设为 {fan_speed}%', 'message_en': f'Fan speed set to {fan_speed}%'})

# ==================== API: 空调 ====================

@app.route('/api/ac', methods=['GET'])
def get_ac_status():
    """获取空调状态"""
    status = db.get_current_status()
    return jsonify({
        'ac_status': status.get('ac_status', 'off'),
        'ac_temperature': status.get('ac_temperature', 26)
    })

@app.route('/api/ac', methods=['POST'])
def control_ac():
    """控制空调"""
    data = request.json
    ac_status = data.get('status', 'off')
    ac_temp = data.get('temperature', 26)
    ac_temp = max(16, min(30, ac_temp))
    
    db.update_status(ac_status=ac_status, ac_temperature=ac_temp)
    return jsonify({
        'ac_status': ac_status,
        'ac_temperature': ac_temp,
        'message': f'空调已{"开启" if ac_status == "on" else "关闭"}，温度设为 {ac_temp}°C',
        'message_en': f'AC {"turned on" if ac_status == "on" else "turned off"}, temp set to {ac_temp}°C'
    })

# ==================== API: 门禁 ====================

@app.route('/api/access/logs', methods=['GET'])
def get_access_logs():
    """获取门禁日志"""
    logs = db.get_access_logs()
    return jsonify(logs)

@app.route('/api/access/verify', methods=['POST'])
def verify_access():
    """验证门禁（人脸识别/RFID）"""
    data = request.json
    face_id = data.get('face_id', data.get('rfid_tag', ''))
    verify_type = data.get('verify_type', 'face')
    persons = db.get_authorized_persons()
    
    # 优先匹配face_id，其次匹配rfid_tag
    for person in persons:
        if person.get('face_id') == face_id or person.get('rfid_tag') == face_id:
            db.add_access_log(person['name'], verify_type, 'granted')
            return jsonify({'granted': True, 'person': person['name'], 'message': f'人脸验证通过, 欢迎 {person["name"]}!', 'message_en': f'Face verified, Welcome {person["name"]}!'})
    
    db.add_access_log('未知人员', verify_type, 'denied')
    return jsonify({'granted': False, 'person': None, 'message': '人脸未识别，访问被拒绝', 'message_en': 'Face not recognized, access denied'})

@app.route('/api/access/persons', methods=['GET'])
def get_persons():
    """获取授权人员列表"""
    persons = db.get_authorized_persons()
    return jsonify(persons)

@app.route('/api/access/persons', methods=['POST'])
def add_person():
    """添加授权人员"""
    data = request.json
    name = data.get('name', '')
    rfid_tag = data.get('rfid_tag', '')
    face_id = data.get('face_id', '')
    success = db.add_authorized_person(name, rfid_tag=rfid_tag, face_id=face_id)
    if success:
        # 同步到人脸识别引擎的已知人脸库
        if face_id:
            face_engine.add_known_face(face_id, name)
        return jsonify({'message': f'已添加授权人员: {name}', 'message_en': f'Authorized person added: {name}'})
    return jsonify({'error': f'人员 {name} 已存在', 'error_en': f'Person {name} already exists'}), 400

# ==================== API: 健康检查 ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """系统健康检查 - 用于前端断线检测"""
    import time
    status = {
        'status': 'ok',
        'timestamp': time.time(),
        'services': {
            'database': True,
            'ha': ha_client.connected,
            'face_recognition': face_engine.simulation_mode is False,
        }
    }
    # 快速检查数据库是否可用
    try:
        db.get_current_status()
    except Exception:
        status['services']['database'] = False
        status['status'] = 'degraded'

    return jsonify(status)

# ==================== API: 统计 ====================

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """获取全部统计信息"""
    stats = db.get_statistics()
    return jsonify(stats)

# ==================== API: YOLOv8 人脸识别 ====================

@app.route('/api/face/recognize', methods=['POST'])
def face_recognize():
    """YOLOv8 人脸识别接口 - 接收摄像头帧进行识别"""
    data = request.json
    image_data = data.get('image', '')

    if not image_data:
        return jsonify({'error': '无图像数据', 'error_en': 'No image data'}), 400

    # 安全解码 Base64（限制 5MB，防止内存攻击）
    try:
        image_bytes = safe_base64_decode(image_data, max_size_mb=5)
    except ValueError as e:
        return jsonify({'error': f'图像数据错误: {str(e)}', 'error_en': f'Image data error: {str(e)}'}), 400

    # 安全解码后直接传递给识别引擎
    import base64
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    result = face_engine.recognize_from_base64(image_b64)
    return jsonify(result)

@app.route('/api/face/status', methods=['GET'])
def face_status():
    """获取人脸识别引擎状态"""
    status = face_engine.get_status()
    return jsonify(status)

@app.route('/api/face/config', methods=['GET'])
def face_get_config():
    """获取人脸识别配置"""
    config = face_engine.config
    status = face_engine.get_status()
    return jsonify({'config': config, 'status': status})

@app.route('/api/face/config', methods=['POST'])
def face_save_config():
    """保存人脸识别配置"""
    data = request.json
    face_engine.save_config(data)
    # 如果从模拟切换到真实模式，尝试加载模型
    if not data.get('simulation_mode', True):
        face_engine.reload_model()
    status = face_engine.get_status()
    return jsonify({'message': '人脸识别配置已保存', 'message_en': 'Face recognition config saved', 'status': status})

@app.route('/api/face/reload', methods=['POST'])
def face_reload():
    """重新加载YOLOv8模型"""
    success = face_engine.reload_model()
    status = face_engine.get_status()
    if success:
        return jsonify({'message': '模型已重新加载', 'message_en': 'Model reloaded', 'status': status})
    return jsonify({'message': '模型未加载，仍使用模拟模式', 'message_en': 'Model not loaded, using simulation mode', 'status': status})

@app.route('/api/face/known', methods=['GET'])
def face_get_known():
    """获取已知人脸列表"""
    known = face_engine.config.get('known_faces', {})
    return jsonify(known)

@app.route('/api/face/known', methods=['POST'])
def face_add_known():
    """添加已知人脸"""
    data = request.json
    face_id = data.get('face_id', '')
    name = data.get('name', '')
    if not face_id or not name:
        return jsonify({'error': '缺少参数', 'error_en': 'Missing parameters'}), 400
    face_engine.add_known_face(face_id, name)
    return jsonify({'message': f'已添加已知人脸: {name} ({face_id})', 'message_en': f'Known face added: {name} ({face_id})'})

@app.route('/api/face/known/<face_id>', methods=['DELETE'])
def face_remove_known(face_id):
    """删除已知人脸"""
    success = face_engine.remove_known_face(face_id)
    if success:
        return jsonify({'message': f'已删除人脸: {face_id}', 'message_en': f'Face removed: {face_id}'})
    return jsonify({'error': f'未找到人脸: {face_id}', 'error_en': f'Face not found: {face_id}'}), 404

# ==================== API: Home Assistant 硬件接口 ====================

@app.route('/api/ha/connection', methods=['GET'])
def ha_test_connection():
    """测试HA连接"""
    result = ha_client.test_connection()
    return jsonify(result)

@app.route('/api/ha/config', methods=['GET'])
def ha_get_config():
    """获取HA系统信息"""
    config = ha_client.get_config()
    mapping = ha_client.get_device_mapping()
    return jsonify({'ha_config': config, 'device_mapping': mapping, 'ha_url': ha_client.base_url})

@app.route('/api/ha/config', methods=['POST'])
def ha_save_config():
    """保存HA连接配置"""
    data = request.json
    ha_client.save_config(
        data.get('ha_url', ''),
        data.get('ha_token', ''),
        data.get('device_mapping')
    )
    return jsonify({'message': '配置已保存', 'message_en': 'Configuration saved'})

@app.route('/api/ha/devices', methods=['GET'])
def ha_get_devices():
    """获取所有设备"""
    devices = ha_client.get_discovered_devices()
    return jsonify(devices)

@app.route('/api/ha/mapping', methods=['POST'])
def ha_update_mapping():
    """更新设备映射"""
    data = request.json
    device_type = data.get('device_type', '')
    entity_id = data.get('entity_id', '')
    ha_client.update_device_mapping(device_type, entity_id)
    return jsonify({'message': '设备映射已更新', 'message_en': 'Device mapping updated'})

@app.route('/api/ha/temperature', methods=['GET'])
def ha_get_temperature():
    """获取HA温度"""
    temp = ha_client.get_temperature()
    return jsonify({'temperature': temp})

@app.route('/api/ha/humidity', methods=['GET'])
def ha_get_humidity():
    """获取HA湿度"""
    humidity = ha_client.get_humidity()
    return jsonify({'humidity': humidity})

@app.route('/api/ha/light', methods=['POST'])
def ha_control_light():
    """通过HA控制灯光"""
    data = request.json
    result = ha_client.control_light(
        action=data.get('action', 'toggle'),
        brightness=data.get('brightness')
    )
    return jsonify(result)

@app.route('/api/ha/fan', methods=['POST'])
def ha_control_fan():
    """通过HA控制风扇"""
    data = request.json
    result = ha_client.control_fan(speed_pct=data.get('speed'))
    return jsonify(result)

@app.route('/api/ha/ac', methods=['POST'])
def ha_control_ac():
    """通过HA控制空调"""
    data = request.json
    result = ha_client.control_ac(
        mode=data.get('mode', 'off'),
        temperature=data.get('temperature')
    )
    return jsonify(result)

@app.route('/api/ha/door', methods=['POST'])
def ha_control_door():
    """通过HA控制门锁"""
    data = request.json
    result = ha_client.control_door(action=data.get('action', 'unlock'))
    return jsonify(result)

@app.route('/api/ha/door/status', methods=['GET'])
def ha_get_door_status():
    """获取HA门状态"""
    status = ha_client.get_door_status()
    return jsonify({'status': status})

@app.route('/api/ha/window/status', methods=['GET'])
def ha_get_window_status():
    """获取HA窗户状态"""
    status = ha_client.get_window_status()
    return jsonify({'status': status})

@app.route('/api/ha/camera', methods=['GET'])
def ha_camera_snapshot():
    """获取摄像头截图"""
    from flask import Response
    image = ha_client.get_camera_image()
    if image:
        return Response(image, mimetype='image/jpeg')
    return jsonify({'error': '无法获取图像'}), 404

# ==================== 启动 ====================

if __name__ == '__main__':
    print("=" * 50)
    print("  智能家居系统 GUI 启动中...")
    print("  请访问: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
