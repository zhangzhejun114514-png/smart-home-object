// ==================== 全局变量 ====================
let tempChart = null;
let currentStatus = {};

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    loadStatus();
    initTempChart();
    loadTempHistory();
    // 每5秒自动刷新状态
    setInterval(loadStatus, 5000);
    // 每30秒刷新图表
    setInterval(loadTempHistory, 30000);
});

// ==================== 时钟 ====================
function updateClock() {
    const now = new Date();
    const locale = I18N.currentLang === 'zh' ? 'zh-CN' : 'en-US';
    const timeStr = now.toLocaleTimeString(locale, { hour12: false });
    const el = document.getElementById('currentTime');
    if (el) el.textContent = timeStr;
}

// ==================== 通知 ====================
function showNotification(message, type = 'info') {
    const el = document.getElementById('notification');
    if (!el) return;
    el.textContent = message;
    el.className = `notification ${type} show`;
    setTimeout(() => { el.className = 'notification hidden'; }, 3000);
}

// ==================== API调用封装 ====================
async function apiGet(url) {
    try {
        const res = await fetch(url);
        return await res.json();
    } catch (e) {
        console.error('API GET error:', e);
        return null;
    }
}

async function apiPost(url, data) {
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await res.json();
    } catch (e) {
        console.error('API POST error:', e);
        return null;
    }
}

// ==================== 加载系统状态 ====================
async function loadStatus() {
    const data = await apiGet('/api/status');
    if (!data) return;
    currentStatus = data;
    updateUI(data);
}

function updateUI(data) {
    // 温度
    const temp = parseFloat(data.temperature).toFixed(1);
    document.getElementById('tempValue').textContent = temp;
    
    // 湿度
    const humidity = data.humidity ? parseFloat(data.humidity).toFixed(0) : '--';
    document.getElementById('humidityValue').textContent = humidity;
    
    // 温度统计
    if (data.statistics && data.statistics.temperature_24h) {
        const s = data.statistics.temperature_24h;
        document.getElementById('tempMax').textContent = s.max ? s.max.toFixed(1) : '--';
        document.getElementById('tempMin').textContent = s.min ? s.min.toFixed(1) : '--';
        document.getElementById('tempAvg').textContent = s.avg ? s.avg.toFixed(1) : '--';
    }
    
    // 温度告警
    const alertEl = document.getElementById('tempAlert');
    if (temp >= 30) {
        alertEl.textContent = t('temp.too_high');
        alertEl.className = 'card-badge danger';
    } else if (temp >= 28) {
        alertEl.textContent = t('temp.high_warn');
        alertEl.className = 'card-badge warning';
    } else {
        alertEl.textContent = t('temp.normal');
        alertEl.className = 'card-badge';
    }
    
    // 风扇
    const fanSpeed = data.fan_speed || 0;
    document.getElementById('fanSpeed').value = fanSpeed;
    document.getElementById('fanSpeedValue').textContent = fanSpeed + '%';
    updateFanAnimation(fanSpeed);
    
    // 门
    updateDoorWindowUI('door', data.door_status);
    updateDoorWindowUI('window', data.window_status);
    
    // 灯光
    const lightOn = data.light_status === 'on';
    const brightness = data.light_brightness || 0;
    document.getElementById('brightnessSlider').value = brightness;
    document.getElementById('brightnessValue').textContent = brightness + '%';
    document.getElementById('bulb').className = lightOn ? 'bulb on' : 'bulb';
    document.getElementById('bulb').style.opacity = brightness / 100;
    document.getElementById('lightIndicator').className = lightOn ? 'light-indicator on' : 'light-indicator';
    
    // 空调
    const acOn = data.ac_status === 'on';
    const acTemp = data.ac_temperature || 26;
    document.getElementById('acTempDisplay').textContent = acTemp;
    document.getElementById('acTempSlider').value = acTemp;
    document.getElementById('acTempSliderValue').textContent = acTemp + '°C';
    document.getElementById('acBadge').textContent = acOn ? t('ac.running') : t('ac.off');
    document.getElementById('acBadge').className = acOn ? 'ac-status-badge on' : 'ac-status-badge';
    document.getElementById('acPowerBtn').className = acOn ? 'btn btn-ac btn-power active' : 'btn btn-ac btn-power';
}

function updateFanAnimation(speed) {
    const blades = document.getElementById('fanBlades');
    blades.className = 'fan-blades';
    if (speed > 70) blades.classList.add('spinning-fast');
    else if (speed > 40) blades.classList.add('spinning-medium');
    else if (speed > 0) blades.classList.add('spinning-slow');
}

function updateDoorWindowUI(type, status) {
    const statusEl = document.getElementById(type + 'Status');
    const iconEl = document.getElementById(type + 'Icon');
    statusEl.textContent = status === 'open' ? t('door.opened') : t('door.closed');
    statusEl.className = 'dw-status ' + status;
    if (iconEl) {
        iconEl.className = 'dw-icon' + (status === 'open' ? ' open' : '');
    }
}

// ==================== 控制操作 ====================

// 风扇控制
async function setFan(speed) {
    const res = await apiPost('/api/fan', { speed: speed });
    if (res) {
        document.getElementById('fanSpeed').value = speed;
        document.getElementById('fanSpeedValue').textContent = speed + '%';
        updateFanAnimation(speed);
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
    }
}

// 门控制
async function toggleDoor() {
    const current = currentStatus.door_status || 'closed';
    const newStatus = current === 'closed' ? 'open' : 'closed';
    const res = await apiPost('/api/door', { status: newStatus });
    if (res) {
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
        loadStatus();
    }
}

// 窗户控制
async function toggleWindow() {
    const current = currentStatus.window_status || 'closed';
    const newStatus = current === 'closed' ? 'open' : 'closed';
    const res = await apiPost('/api/window', { status: newStatus });
    if (res) {
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
        loadStatus();
    }
}

// 灯光控制
async function setLight(status, brightness) {
    const res = await apiPost('/api/light', { status: status, brightness: brightness });
    if (res) {
        document.getElementById('brightnessSlider').value = brightness;
        document.getElementById('brightnessValue').textContent = brightness + '%';
        document.getElementById('bulb').className = status === 'on' ? 'bulb on' : 'bulb';
        document.getElementById('bulb').style.opacity = brightness / 100;
        document.getElementById('lightIndicator').className = status === 'on' ? 'light-indicator on' : 'light-indicator';
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
    }
}

// 空调控制
async function toggleAC() {
    const current = currentStatus.ac_status || 'off';
    const newStatus = current === 'off' ? 'on' : 'off';
    const temp = currentStatus.ac_temperature || 26;
    const res = await apiPost('/api/ac', { status: newStatus, temperature: temp });
    if (res) {
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
        loadStatus();
    }
}

async function adjustAC(delta) {
    const current = currentStatus.ac_temperature || 26;
    const newTemp = Math.max(16, Math.min(30, current + delta));
    const status = currentStatus.ac_status === 'on' ? 'on' : 'on'; // 调温度自动开
    const res = await apiPost('/api/ac', { status: 'on', temperature: newTemp });
    if (res) {
        const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
        showNotification(msg, 'success');
        loadStatus();
    }
}

// ==================== 远程控制 ====================
async function remoteControl(action) {
    switch(action) {
        case 'light_on':
            await setLight('on', 100);
            break;
        case 'light_off':
            await setLight('off', 0);
            break;
        case 'ac_on':
            await apiPost('/api/ac', { status: 'on', temperature: 26 });
            showNotification(t('notify.ac_on'), 'success');
            loadStatus();
            break;
        case 'ac_off':
            await apiPost('/api/ac', { status: 'off', temperature: 26 });
            showNotification(t('notify.ac_off'), 'success');
            loadStatus();
            break;
        case 'fan_on':
            await setFan(60);
            break;
        case 'fan_off':
            await setFan(0);
            break;
        case 'door_open':
            await toggleDoor();
            break;
        case 'door_close':
            await toggleDoor();
            break;
    }
}

// ==================== 温度趋势图 ====================
function initTempChart() {
    const ctx = document.getElementById('tempChart');
    if (!ctx) return;
    
    tempChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: t('chart.temp'),
                    data: [],
                    borderColor: '#00e5ff',
                    backgroundColor: 'rgba(0, 229, 255, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#00e5ff'
                },
                {
                    label: t('chart.humidity'),
                    data: [],
                    borderColor: '#00b4d8',
                    backgroundColor: 'rgba(0, 180, 216, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#00b4d8',
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#8ba4b8',
                        font: { size: 11 },
                        usePointStyle: true,
                        pointStyleWidth: 8
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 25, 35, 0.9)',
                    borderColor: '#2a4a5e',
                    borderWidth: 1,
                    titleColor: '#e8f0f8',
                    bodyColor: '#8ba4b8',
                    padding: 12
                }
            },
            scales: {
                x: {
                    ticks: { color: '#5a7a8e', maxTicksLimit: 10, font: { size: 10 } },
                    grid: { color: 'rgba(42, 74, 94, 0.3)' }
                },
                y: {
                    ticks: { color: '#5a7a8e', font: { size: 10 } },
                    grid: { color: 'rgba(42, 74, 94, 0.3)' },
                    title: { display: true, text: '°C', color: '#5a7a8e' }
                },
                y1: {
                    position: 'right',
                    ticks: { color: '#5a7a8e', font: { size: 10 } },
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: '%', color: '#5a7a8e' },
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

async function loadTempHistory() {
    const data = await apiGet('/api/temperature?hours=24');
    if (!data || !tempChart) return;
    
    // 数据按时间升序（API返回降序，需要反转）
    const reversed = [...data].reverse();
    const labels = reversed.map(d => {
        const dt = new Date(d.timestamp);
        const locale = I18N.currentLang === 'zh' ? 'zh-CN' : 'en-US';
        return dt.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    });
    const temps = reversed.map(d => d.temperature);
    const humidities = reversed.map(d => d.humidity);
    
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = temps;
    tempChart.data.datasets[1].data = humidities;
    tempChart.update('none');
}

// ==================== 滑块事件监听 ====================
document.addEventListener('DOMContentLoaded', () => {
    // 风扇滑块
    const fanSlider = document.getElementById('fanSpeed');
    if (fanSlider) {
        fanSlider.addEventListener('input', function() {
            document.getElementById('fanSpeedValue').textContent = this.value + '%';
            updateFanAnimation(parseInt(this.value));
        });
        fanSlider.addEventListener('change', function() {
            setFan(parseInt(this.value));
        });
    }
    
    // 亮度滑块
    const brightnessSlider = document.getElementById('brightnessSlider');
    if (brightnessSlider) {
        brightnessSlider.addEventListener('input', function() {
            document.getElementById('brightnessValue').textContent = this.value + '%';
            const val = parseInt(this.value);
            document.getElementById('bulb').style.opacity = val / 100;
            if (val > 0) {
                document.getElementById('bulb').className = 'bulb on';
                document.getElementById('lightIndicator').className = 'light-indicator on';
            }
        });
        brightnessSlider.addEventListener('change', function() {
            const val = parseInt(this.value);
            setLight(val > 0 ? 'on' : 'off', val);
        });
    }
    
    // 空调温度滑块
    const acTempSlider = document.getElementById('acTempSlider');
    if (acTempSlider) {
        acTempSlider.addEventListener('input', function() {
            document.getElementById('acTempSliderValue').textContent = this.value + '°C';
        });
        acTempSlider.addEventListener('change', function() {
            adjustAC(0); // 直接用滑块值
            // override: 直接设置温度
            const temp = parseInt(this.value);
            apiPost('/api/ac', { status: 'on', temperature: temp }).then(res => {
                if (res) {
                    showNotification(res.message, 'success');
                    loadStatus();
                }
            });
        });
    }
});
