from flask import Flask, render_template, jsonify, request
from database import db
from datetime import datetime

app = Flask(__name__)

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
    return jsonify({'door_status': new_status, 'message': f'门已{("打开" if new_status == "open" else "关闭")}'})

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
    return jsonify({'window_status': new_status, 'message': f'窗户已{("打开" if new_status == "open" else "关闭")}'})

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
        'message': f'灯光已{("打开" if light_status == "on" else "关闭")}，亮度: {brightness}%'
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
    return jsonify({'fan_speed': fan_speed, 'message': f'风扇速度已设为 {fan_speed}%'})

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
        'message': f'空调已{("开启" if ac_status == "on" else "关闭")}，温度设为 {ac_temp}°C'
    })

# ==================== API: 门禁 ====================

@app.route('/api/access/logs', methods=['GET'])
def get_access_logs():
    """获取门禁日志"""
    logs = db.get_access_logs()
    return jsonify(logs)

@app.route('/api/access/verify', methods=['POST'])
def verify_access():
    """验证门禁（模拟）"""
    data = request.json
    rfid_tag = data.get('rfid_tag', '')
    persons = db.get_authorized_persons()
    
    for person in persons:
        if person.get('rfid_tag') == rfid_tag:
            db.add_access_log(person['name'], 'rfid', 'granted')
            return jsonify({'granted': True, 'person': person['name'], 'message': f'欢迎, {person["name"]}!'})
    
    db.add_access_log('未知人员', 'rfid', 'denied')
    return jsonify({'granted': False, 'person': None, 'message': '未授权，访问被拒绝'})

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
    success = db.add_authorized_person(name, rfid_tag=rfid_tag)
    if success:
        return jsonify({'message': f'已添加授权人员: {name}'})
    return jsonify({'error': f'人员 {name} 已存在'}), 400

# ==================== API: 统计 ====================

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """获取全部统计信息"""
    stats = db.get_statistics()
    return jsonify(stats)

# ==================== 启动 ====================

if __name__ == '__main__':
    print("=" * 50)
    print("  智能家居系统 GUI 启动中...")
    print("  请访问: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
