// ==================== 门禁管理页面 JS ====================

// 摄像头流引用
let cameraStream = null;
let isScanning = false;
let scanInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    loadPersons();
    loadAccessLogs();
});

// 时钟
function updateClock() {
    const now = new Date();
    const el = document.getElementById('currentTime');
    const locale = I18N.currentLang === 'zh' ? 'zh-CN' : 'en-US';
    if (el) el.textContent = now.toLocaleTimeString(locale, { hour12: false });
}

// 通知
function showNotification(message, type = 'info') {
    const el = document.getElementById('notification');
    if (!el) return;
    el.textContent = message;
    el.className = `notification ${type} show`;
    setTimeout(() => { el.className = 'notification hidden'; }, 3000);
}

// API
async function apiGet(url) {
    try {
        const res = await fetch(url);
        return await res.json();
    } catch (e) {
        console.error('API error:', e);
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
        console.error('API error:', e);
        return null;
    }
}

// ==================== 摄像头控制 ====================

async function startCamera() {
    const video = document.getElementById('faceVideo');
    const overlay = document.getElementById('faceOverlay');
    const indicator = document.getElementById('faceIndicator');
    const scanRing = document.getElementById('scanningRing');

    if (cameraStream) {
        // 已开启，关闭摄像头
        stopCamera();
        return;
    }

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: 640, height: 480 }
        });
        video.srcObject = cameraStream;
        video.style.display = 'block';
        overlay.style.display = 'none';

        // 更新按钮文字
        const btn = document.querySelector('[data-i18n="access.camera_start"]');
        if (btn) {
            const lang = I18N.currentLang;
            btn.textContent = lang === 'zh' ? '关闭摄像头' : 'Stop Camera';
        }

        // 显示扫描指示
        indicator.style.display = 'flex';
        scanRing.classList.add('active');

        showNotification(
            I18N.currentLang === 'zh' ? '摄像头已启动，开始实时人脸识别' : 'Camera started, real-time face recognition active',
            'success'
        );

        // 启动实时人脸扫描（发送帧到后端YOLOv8识别）
        startRealtimeScanning();

    } catch (err) {
        console.error('Camera error:', err);
        showNotification(
            I18N.currentLang === 'zh' ? '无法访问摄像头: ' + err.message : 'Cannot access camera: ' + err.message,
            'error'
        );
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }

    const video = document.getElementById('faceVideo');
    const overlay = document.getElementById('faceOverlay');
    const indicator = document.getElementById('faceIndicator');
    const scanRing = document.getElementById('scanningRing');

    video.srcObject = null;
    video.style.display = 'none';
    overlay.style.display = 'flex';
    indicator.style.display = 'flex';
    scanRing.classList.remove('active');

    // 更新按钮文字
    const btn = document.querySelector('[data-i18n="access.camera_start"]');
    if (btn) {
        const lang = I18N.currentLang;
        btn.textContent = lang === 'zh' ? '启动摄像头' : 'Start Camera';
    }

    // 停止实时扫描
    if (scanInterval) {
        clearInterval(scanInterval);
        scanInterval = null;
    }
    isScanning = false;

    showNotification(
        I18N.currentLang === 'zh' ? '摄像头已关闭' : 'Camera stopped',
        'info'
    );
}

// ==================== 实时人脸扫描（YOLOv8后端识别） ====================

function startRealtimeScanning() {
    const video = document.getElementById('faceVideo');
    const canvas = document.getElementById('faceCanvas');
    const ctx = canvas.getContext('2d');
    const indicator = document.getElementById('faceIndicator');

    canvas.width = 640;
    canvas.height = 480;

    // 每2秒发送一帧到后端进行YOLOv8人脸识别
    scanInterval = setInterval(async () => {
        if (!cameraStream || isScanning) return;
        isScanning = true;

        try {
            // 绘制当前帧到canvas
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageData = canvas.toDataURL('image/jpeg', 0.8);

            // 发送到后端YOLOv8识别接口
            const res = await fetch('/api/face/recognize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageData })
            });
            const result = await res.json();

            if (result && result.detected) {
                handleFaceResult(result);
            }
        } catch (e) {
            console.error('Face scan error:', e);
        } finally {
            isScanning = false;
        }
    }, 2000);
}

// 处理YOLOv8识别结果
async function handleFaceResult(result) {
    const indicator = document.getElementById('faceIndicator');
    const resultEl = document.getElementById('accessResult');

    if (result.face_id) {
        // 识别到人脸，自动验证
        const res = await apiPost('/api/access/verify', {
            face_id: result.face_id,
            verify_type: 'face'
        });

        if (res) {
            if (res.granted) {
                indicator.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="#00e676" stroke-width="2" style="width:24px;height:24px">
                        <path d="M20 6L9 17l-5-5"/>
                    </svg>
                    <span style="color:#00e676">${res.person} - ${I18N.currentLang === 'zh' ? '已识别' : 'Recognized'}</span>
                `;
                resultEl.textContent = res.message;
                resultEl.className = 'access-result granted';
                showNotification(
                    I18N.currentLang === 'zh' ? `人脸验证通过: ${res.person}` : `Face verified: ${res.person}`,
                    'success'
                );
            } else {
                indicator.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="#ff1744" stroke-width="2" style="width:24px;height:24px">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="15" y1="9" x2="9" y2="15"/>
                        <line x1="9" y1="9" x2="15" y2="15"/>
                    </svg>
                    <span style="color:#ff1744">${I18N.currentLang === 'zh' ? '未授权人员' : 'Unauthorized'}</span>
                `;
                resultEl.textContent = res.message;
                resultEl.className = 'access-result denied';
                showNotification(t('notify.access_denied'), 'error');
            }
            loadAccessLogs();
        }
    }
}

// ==================== 人脸识别模拟 ====================

// 人脸ID映射
const FACE_ID_MAP = {
    'admin': 'FACE001',
    'family_a': 'FACE002',
    'unknown': 'FACE999'
};

async function simulateFace(faceRole) {
    const faceCamera = document.getElementById('faceCamera');
    const scanRing = document.getElementById('scanningRing');
    const indicator = document.getElementById('faceIndicator');
    const resultEl = document.getElementById('accessResult');

    const face_id = FACE_ID_MAP[faceRole] || 'FACE000';

    // 扫描动画
    faceCamera.classList.add('scanning');
    scanRing.classList.add('active');
    indicator.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="#ffd600" stroke-width="2" class="face-icon" style="animation:spin 1s linear infinite">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
        </svg>
        <span data-i18n="access.face_scanning">${I18N.currentLang === 'zh' ? '正在识别人脸...' : 'Scanning face...'}</span>
    `;
    resultEl.textContent = t('access.verifying');
    resultEl.className = 'access-result';

    // 模拟YOLOv8处理延迟
    setTimeout(async () => {
        const res = await apiPost('/api/access/verify', {
            face_id: face_id,
            verify_type: 'face'
        });

        faceCamera.classList.remove('scanning');
        scanRing.classList.remove('active');

        if (res) {
            if (res.granted) {
                indicator.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="#00e676" stroke-width="2" class="face-icon">
                        <path d="M20 6L9 17l-5-5"/>
                    </svg>
                    <span style="color:#00e676">${res.person} - ${I18N.currentLang === 'zh' ? '已识别' : 'Recognized'}</span>
                `;
                resultEl.textContent = res.message;
                resultEl.className = 'access-result granted';
                showNotification(
                    I18N.currentLang === 'zh' ? `人脸验证通过: ${res.person}` : `Face verified: ${res.person}`,
                    'success'
                );
            } else {
                indicator.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="#ff1744" stroke-width="2" class="face-icon">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="15" y1="9" x2="9" y2="15"/>
                        <line x1="9" y1="9" x2="15" y2="15"/>
                    </svg>
                    <span style="color:#ff1744">${I18N.currentLang === 'zh' ? '未授权人员' : 'Unauthorized'}</span>
                `;
                resultEl.textContent = res.message;
                resultEl.className = 'access-result denied';
                showNotification(t('notify.access_denied'), 'error');
            }
            // 刷新日志
            loadAccessLogs();
        }
    }, 1200);
}

// ==================== 授权人员管理 ====================

async function loadPersons() {
    const persons = await apiGet('/api/access/persons');
    if (!persons) return;

    const listEl = document.getElementById('personList');
    let html = '';

    persons.forEach((p, i) => {
        const initial = p.name.charAt(0);
        const colors = ['#00e5ff', '#00e676', '#7c4dff', '#ff9100', '#ff1744'];
        const color = colors[i % colors.length];
        const faceIdDisplay = p.face_id || t('access.unset');
        html += `
            <div class="person-item">
                <div class="person-info">
                    <div class="person-avatar" style="background: ${color}">${initial}</div>
                    <div>
                        <div class="person-name">${p.name}</div>
                        <div class="person-rfid">${I18N.currentLang === 'zh' ? '人脸ID' : 'Face ID'}: ${faceIdDisplay}</div>
                    </div>
                </div>
            </div>
        `;
    });

    listEl.innerHTML = html || '<div class="loading">' + t('access.no_persons') + '</div>';
}

async function addPerson() {
    const nameInput = document.getElementById('newPersonName');
    const rfidInput = document.getElementById('newPersonRFID');
    const name = nameInput.value.trim();
    const faceId = rfidInput.value.trim();

    if (!name) {
        showNotification(t('notify.enter_name'), 'error');
        return;
    }

    const res = await apiPost('/api/access/persons', { name: name, face_id: faceId });
    if (res) {
        if (res.message) {
            const msg = I18N.currentLang === 'en' ? (res.message_en || res.message) : res.message;
            showNotification(msg, 'success');
            nameInput.value = '';
            rfidInput.value = '';
            loadPersons();
        } else if (res.error) {
            const err = I18N.currentLang === 'en' ? (res.error_en || res.error) : res.error;
            showNotification(err, 'error');
        }
    }
}

// ==================== 门禁日志 ====================

async function loadAccessLogs() {
    const logs = await apiGet('/api/access/logs');
    if (!logs) return;

    const body = document.getElementById('accessLogBody');
    let html = '';

    logs.forEach(log => {
        const dt = new Date(log.timestamp);
        const locale = I18N.currentLang === 'zh' ? 'zh-CN' : 'en-US';
        const timeStr = dt.toLocaleString(locale);
        const statusClass = log.status === 'granted' ? 'granted' : 'denied';
        const statusText = log.status === 'granted' ? t('access.log_granted') : t('access.log_denied');

        html += `
            <tr>
                <td>${timeStr}</td>
                <td>${log.person_name}</td>
                <td>${log.access_type.toUpperCase()}</td>
                <td><span class="status-tag ${statusClass}">${statusText}</span></td>
            </tr>
        `;
    });

    body.innerHTML = html || '<tr><td colspan="4">' + t('access.no_records') + '</td></tr>';
}
