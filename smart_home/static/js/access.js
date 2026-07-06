// ==================== 门禁管理页面 JS ====================

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
    if (el) el.textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
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

// ==================== 门禁验证模拟 ====================
async function simulateAccess(rfidTag) {
    const scanArea = document.querySelector('.scan-area');
    const resultEl = document.getElementById('accessResult');
    
    // 扫描动画
    scanArea.classList.add('scanning');
    resultEl.textContent = '验证中...';
    resultEl.className = 'access-result';
    
    // 模拟延迟
    setTimeout(async () => {
        const res = await apiPost('/api/access/verify', { rfid_tag: rfidTag });
        scanArea.classList.remove('scanning');
        
        if (res) {
            if (res.granted) {
                resultEl.textContent = `${res.message}`;
                resultEl.className = 'access-result granted';
                showNotification(`门禁验证通过: ${res.person}`, 'success');
            } else {
                resultEl.textContent = res.message;
                resultEl.className = 'access-result denied';
                showNotification('门禁验证失败: 未授权人员', 'error');
            }
            // 刷新日志
            loadAccessLogs();
        }
    }, 800);
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
        html += `
            <div class="person-item">
                <div class="person-info">
                    <div class="person-avatar" style="background: ${color}">${initial}</div>
                    <div>
                        <div class="person-name">${p.name}</div>
                        <div class="person-rfid">RFID: ${p.rfid_tag || '未设置'}</div>
                    </div>
                </div>
            </div>
        `;
    });
    
    listEl.innerHTML = html || '<div class="loading">暂无授权人员</div>';
}

async function addPerson() {
    const nameInput = document.getElementById('newPersonName');
    const rfidInput = document.getElementById('newPersonRFID');
    const name = nameInput.value.trim();
    const rfid = rfidInput.value.trim();
    
    if (!name) {
        showNotification('请输入姓名', 'error');
        return;
    }
    
    const res = await apiPost('/api/access/persons', { name: name, rfid_tag: rfid });
    if (res) {
        if (res.message) {
            showNotification(res.message, 'success');
            nameInput.value = '';
            rfidInput.value = '';
            loadPersons();
        } else if (res.error) {
            showNotification(res.error, 'error');
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
        const timeStr = dt.toLocaleString('zh-CN');
        const statusClass = log.status === 'granted' ? 'granted' : 'denied';
        const statusText = log.status === 'granted' ? '通过' : '拒绝';
        
        html += `
            <tr>
                <td>${timeStr}</td>
                <td>${log.person_name}</td>
                <td>${log.access_type.toUpperCase()}</td>
                <td><span class="status-tag ${statusClass}">${statusText}</span></td>
            </tr>
        `;
    });
    
    body.innerHTML = html || '<tr><td colspan="4">暂无记录</td></tr>';
}
