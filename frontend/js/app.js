const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentUser = null;
let isAdmin = false;
let isRegistered = false;
let userNickname = null;
let isTechAdmin = false;
let selectedBulkMembers = [];
let currentHistoryMember = null;
let currentRoleChangeMember = null;
// Инициализация
async function init() {
    try {
        const initData = tg.initData || '';
        if (!initData) {
            tg.showAlert('⚠️ Mini App работает только внутри Telegram!');
            return;
        }

        const response = await fetch('/api/auth', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({initData})
        });

        const data = await response.json();
        currentUser = data.user;
        isAdmin = data.is_admin;
        isRegistered = data.is_registered;
        userNickname = data.nickname;

        // 🔥 Проверка тех админа
        const techAdminResponse = await fetch(`/api/is_tech_admin/${currentUser.id}`);
        const techAdminData = await techAdminResponse.json();
        isTechAdmin = techAdminData.is_tech_admin;

        tg.MainButton.setParams({color: tg.themeParams.button_color || '#3390ec'});
        tg.setHeaderColor(tg.themeParams.bg_color || '#1a1a2e');

        showPage('home-page');
        renderUserInfo();

        if (isAdmin || isTechAdmin) {
            document.getElementById('admin-btn').style.display = 'block';
        }

        document.body.classList.add('loaded');
    } catch (error) {
        tg.showAlert(`❌ Ошибка авторизации: ${error.message}`);
    }
}
// Навигация
function navigate(page) {
    showPage(page + '-page');

    if (page === 'profile' && isRegistered) {
        loadProfile();
    } else if (page === 'clan_list') {
        loadClanList();
    } else if (page === 'stats') {
        loadStats('week');
    } else if (page === 'admin' && isAdmin) {
        renderAdminMenu();
    }
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
}

// Рендер информации о пользователе
function renderUserInfo() {
    const userInfo = document.getElementById('user-info');
    userInfo.innerHTML = `
        <div class="card">
            <p>👤 <b>${currentUser.first_name} ${currentUser.last_name || ''}</b></p>
            <p>@${currentUser.username || 'Нет username'}</p>
            <p>${isRegistered ? '✅ Зарегистрирован' : '⏳ Не зарегистрирован'}</p>
            ${userNickname ? `<p>🎮 Ник: <b>${userNickname}</b></p>` : ''}
            ${isAdmin ? '<p>🛡 <b>Администратор</b></p>' : ''}
        </div>
    `;
}

// Загрузка профиля
async function loadProfile() {
    try {
        const response = await fetch(`/api/profile/${currentUser.id}`);
        const data = await response.json();

        document.getElementById('profile-data').innerHTML = `
            <div class="card">
                <p>🎮 <b>${data.nick}</b></p>
                <p>🆔 <code>${data.steam_id}</code></p>
                <p>🎖 Роль: <span class="role-badge">${data.role}</span></p>
                <p>⚠️ Предупреждения: ${data.warns}</p>
                <p>👏 Похвалы: ${data.praises}</p>
                <p>📊 Рейтинг: ${data.score}</p>
                <p>📌 Статус: ${data.desirable}</p>
            </div>
        `;
    } catch (error) {
        document.getElementById('profile-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки профиля</div>';
    }
}

// Загрузка списка клана
async function loadClanList() {
    try {
        const response = await fetch('/api/clan_members');
        const data = await response.json();

        document.getElementById('clan-members').innerHTML = data.members
            .map(m => `<div class="card" onclick="selectMember('${m.replace(/'/g, "\\'")}')">${m}</div>`)
            .join('');
    } catch (error) {
        document.getElementById('clan-members').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}

// =========================
// 🔄 ОБНОВЛЁННЫЙ CLAN LIST
// =========================
function selectMember(member) {
    selectedMember = member;
    document.getElementById('member-actions-title').innerText = `Действия: ${member}`;
    document.getElementById('member-info-display').innerHTML = `<p>👤 <strong>${member}</strong></p>`;

    let adminButtons = '';
    if (isAdmin) {
        adminButtons = `
            <button class="btn" onclick="showMemberHistoryPage('${member}')">📋 История</button>
            <button class="btn" onclick="showChangeRolePage('${member}')">🎖 Сменить разряд</button>
        `;
    }

    document.getElementById('admin-actions').innerHTML = `
        ${adminButtons}
        <div id="admin-actions-original">
            <button class="btn btn-warning" onclick="showPage('pred-page')">⚠ Предупреждение</button>
        </div>
    `;

    document.getElementById('praise-reason').value = '';
    document.getElementById('complaint-reason').value = '';
    document.getElementById('pred-reason').value = '';

    showPage('member_actions-page');
}
// Отправка похвалы
async function sendPraise() {
    const reason = document.getElementById('praise-reason').value.trim();

    if (!reason) {
        tg.showAlert('Введите причину похвалы');
        return;
    }

    try {
        const response = await fetch(`/api/praise?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({member: selectedMember, reason: reason})
        });

        const data = await response.json();

        if (response.ok) {
            tg.showAlert(data.message);
            document.getElementById('praise-reason').value = '';
            navigate('clan_list');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка отправки: ' + error.message);
    }
}

// Отправка жалобы
async function sendComplaint() {
    const reason = document.getElementById('complaint-reason').value.trim();

    if (!reason) {
        tg.showAlert('Введите причину жалобы');
        return;
    }

    try {
        const response = await fetch(`/api/complaint?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({member: selectedMember, reason: reason})
        });

        const data = await response.json();

        if (response.ok) {
            tg.showAlert(data.message);
            document.getElementById('complaint-reason').value = '';
            navigate('clan_list');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка отправки: ' + error.message);
    }
}

// Выдача преда (админы)
async function sendPred() {
    const reason = document.getElementById('pred-reason').value.trim();

    if (!reason) {
        tg.showAlert('Введите причину предупреждения');
        return;
    }

    try {
        const response = await fetch(`/api/pred?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({member: selectedMember, reason: reason})
        });

        const data = await response.json();

        if (response.ok) {
            tg.showAlert(data.message);
            document.getElementById('pred-reason').value = '';
            navigate('clan_list');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка отправки: ' + error.message);
    }
}

// Загрузка статистики
async function loadStats(period) {
    try {
        const response = await fetch(`/api/stats/${period}`);
        const data = await response.json();

        if (data.top.length === 0) {
            document.getElementById('stats-data').innerHTML = '<div class="card">📭 Пока нет похвал</div>';
        } else {
            document.getElementById('stats-data').innerHTML = data.top
                .map((t, i) => `<div class="card"><b>${i+1}. ${t.nick}</b> — ${t.count} 👏</div>`)
                .join('');
        }
    } catch (error) {
        document.getElementById('stats-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}

// =========================
// 🔄 ОБНОВЛЁННЫЙ ADMIN MENU
// =========================
function renderAdminMenu() {
    let techAdminButtons = '';
    if (isTechAdmin) {
        techAdminButtons = `

            <button class="btn btn-primary" onclick="loadDevlogs()">📝 Devlogs</button>
        `;
    }

    document.getElementById('admin-data').innerHTML = `
        ${techAdminButtons}
        <button class="btn btn-primary" onclick="showBulkPraise()">🏆 Массовая похвала</button>
        <button class="btn" onclick="loadComplaints()">⚖ Жалобы</button>
        <button class="btn" onclick="loadLogs()">📝 Логи</button>
        <button class="btn" onclick="loadApplications()">📬 Заявки</button>
        <button class="btn btn-primary" onclick="loadNotifications()">📢 Оповещения</button>
    `;
}


// Загрузка заявок
async function loadApplications() {
    showPage('applications-page');
    try {
        const response = await fetch(`/api/applications?user_id=${currentUser.id}`);
        const data = await response.json();

        if (data.applications.length === 0) {
            document.getElementById('applications-data').innerHTML = '<div class="card">📭 Нет заявок</div>';
        } else {
            document.getElementById('applications-data').innerHTML = data.applications
                .map(a => `
                    <div class="card">
                        <p><b>📬 #${a.id}</b> | ${a.nick}</p>
                        <p>🆔 ${a.steam_id}</p>
                        <p>👤 ${a.tg_username}</p>
                        <p>🕒 ${a.date}</p>
                        <p><span class="status-badge status-${a.status === 'ожидает' ? 'waiting' : a.status === 'принят' ? 'accepted' : 'rejected'}">${a.status}</span></p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('applications-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}

// Загрузка логов
async function loadLogs() {
    showPage('logs-page');
    try {
        const response = await fetch(`/api/logs?user_id=${currentUser.id}`);
        const data = await response.json();

        if (data.logs.length === 0) {
            document.getElementById('logs-data').innerHTML = '<div class="card">📭 Логи пусты</div>';
        } else {
            document.getElementById('logs-data').innerHTML = data.logs
                .map(l => `
                    <div class="card">
                        <p><b>${l[4]}</b></p>
                        <p>${l[0]} | ${l[1]} → ${l[3]}</p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('logs-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}

// Загрузка жалоб
async function loadComplaints() {
    showPage('complaints-page');
    try {
        const response = await fetch(`/api/complaints?user_id=${currentUser.id}`);
        const data = await response.json();

        if (data.complaints.length === 0) {
            document.getElementById('complaints-data').innerHTML = '<div class="card">📭 Нет активных жалоб</div>';
        } else {
            document.getElementById('complaints-data').innerHTML = data.complaints
                .map(c => `
                    <div class="card">
                        <p><b>⚖ Жалоба #${c.index}</b></p>
                        <p>👤 От: ${c.from_user}</p>
                        <p>🎯 На: ${c.to_member}</p>
                        <p>📝 ${c.reason}</p>
                        <p>🕒 ${c.date}</p>
                        <p><span class="status-badge status-active">${c.status}</span></p>
                        <div class="action-buttons">
                            <button onclick="closeComplaint(${c.index}, 'pred')" class="admin-btn">⚠ Пред + закрыть</button>
                            <button onclick="closeComplaint(${c.index}, 'noaction')">❌ Закрыть</button>
                        </div>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('complaints-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}

// Закрытие жалобы
async function closeComplaint(index, action) {
    const actionText = action === 'pred' ? 'Пред + закрыть' : 'Закрыть';

    if (!confirm(`Вы уверены, что хотите ${actionText.toLowerCase()} эту жалобу?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/complaint/close?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({index: index, action: action})
        });

        const data = await response.json();

        if (response.ok) {
            tg.showAlert(data.message);
            loadComplaints();
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка: ' + error.message);
    }
}

// Загрузка разрядов
async function loadRoles() {
    showPage('roles-page');
    try {
        const response = await fetch('/api/roles');
        const data = await response.json();

        document.getElementById('roles-data').innerHTML = `
            <div class="card">
                <h3>🪖 Сквадные (${data.сквадной.length})</h3>
                ${data.сквадной.map(m => `<span class="role-badge">${m}</span>`).join('')}
            </div>
            <div class="card">
                <h3>🎯 Пехи (${data.пех.length})</h3>
                ${data.пех.map(m => `<span class="role-badge">${m}</span>`).join('')}
            </div>
            <div class="card">
                <h3>🔧 Техи (${data.тех.length})</h3>
                ${data.тех.map(m => `<span class="role-badge">${m}</span>`).join('')}
            </div>
        `;
    } catch (error) {
        document.getElementById('roles-data').innerHTML = '<div class="error-message">❌ Ошибка загрузки</div>';
    }
}
// =========================
// 📢 ОПОВЕЩЕНИЯ
// =========================
function toggleScheduleTime() {
    const schedule = document.getElementById('notification-schedule').value;
    document.getElementById('schedule-time-container').style.display =
        schedule === 'schedule' ? 'block' : 'none';
}

function showCreateNotification() {
    showPage('create-notification-page');
}

async function sendNotification() {
    const audience = document.getElementById('notification-audience').value;
    const text = document.getElementById('notification-text').value.trim();
    const schedule = document.getElementById('notification-schedule').value;

    if (!text) {
        tg.showAlert('Введите текст оповещения');
        return;
    }

    let scheduleTime = "now";
    if (schedule === 'schedule') {
        const datetime = document.getElementById('notification-datetime').value;
        if (!datetime) {
            tg.showAlert('Выберите дату и время');
            return;
        }
        // Конвертация в формат DD.MM.YYYY HH:MM
        const date = new Date(datetime);
        scheduleTime = date.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        }).replace(',', '');
    }

    try {
        const response = await fetch(`/api/notification?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                audience, text, schedule_time: scheduleTime
            })
        });

        const data = await response.json();
        if (response.ok) {
            tg.showAlert(data.message);
            loadNotifications();
            navigate('notifications');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка: ' + error.message);
    }
}

async function loadNotifications() {
    showPage('notifications-page');
    try {
        const response = await fetch(`/api/notifications?user_id=${currentUser.id}`);
        const data = await response.json();

        if (data.notifications.length === 0) {
            document.getElementById('notifications-list').innerHTML = '<p>📭 Нет оповещений</p>';
        } else {
            document.getElementById('notifications-list').innerHTML = data.notifications
                .map(n => `
                    <div class="card">
                        <p><strong>📢 ${n.audience}</strong></p>
                        <p>${n.text}</p>
                        <p><small>👤 ${n.author} | 🕒 ${n.created} | 📅 ${n.schedule}</small></p>
                        <p><span class="status-${n.status}">${n.status}</span></p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('notifications-list').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}
// =========================
// 📝 DEVLOGS
// =========================
function showCreateDevlog() {
    showPage('create-devlog-page');
}

async function sendDevlog() {
    const title = document.getElementById('devlog-title').value.trim();
    const content = document.getElementById('devlog-content').value.trim();

    if (!title || !content) {
        tg.showAlert('Заполните заголовок и содержание');
        return;
    }

    try {
        const response = await fetch(`/api/devlog?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, content})
        });

        const data = await response.json();
        if (response.ok) {
            tg.showAlert(data.message);
            loadDevlogs();
            navigate('devlogs');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка: ' + error.message);
    }
}

async function loadDevlogs() {
    showPage('devlogs-page');
    try {
        const response = await fetch('/api/devlogs');
        const data = await response.json();

        if (data.devlogs.length === 0) {
            document.getElementById('devlogs-list').innerHTML = '<p>📭 Нет devlogs</p>';
        } else {
            document.getElementById('devlogs-list').innerHTML = data.devlogs
                .reverse()
                .map(d => `
                    <div class="card">
                        <h3>📝 ${d.title}</h3>
                        <p>${d.content}</p>
                        <p><small>👤 ${d.author} | 🕒 ${d.date}</small></p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('devlogs-list').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

// =========================
// 🏆 МАССОВАЯ ПОХВАЛА
// =========================
async function showBulkPraise() {
    showPage('bulk-praise-page');
    selectedBulkMembers = [];
    updateBulkCount();

    try {
        const response = await fetch('/api/clan_members');
        const data = await response.json();

        document.getElementById('bulk-members-list').innerHTML = data.members
            .map(m => `
                <div class="card selectable-member" onclick="toggleBulkSelect('${m}')">
                    <span id="bulk-check-${m}">⬜</span> ${m}
                </div>
            `).join('');
    } catch (error) {
        document.getElementById('bulk-members-list').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

function toggleBulkSelect(member) {
    const index = selectedBulkMembers.indexOf(member);
    const checkbox = document.getElementById(`bulk-check-${member}`);

    if (index === -1) {
        selectedBulkMembers.push(member);
        checkbox.innerText = '✅';
    } else {
        selectedBulkMembers.splice(index, 1);
        checkbox.innerText = '⬜';
    }
    updateBulkCount();
}

function updateBulkCount() {
    document.getElementById('bulk-selected-count').innerText = `Выбрано: ${selectedBulkMembers.length}`;
}

function selectAllMembers() {
    // Загрузить всех если ещё не загружены
    const members = document.querySelectorAll('.selectable-member');
    members.forEach(m => {
        const name = m.innerText.replace('✅', '').replace('⬜', '').trim();
        if (!selectedBulkMembers.includes(name)) {
            selectedBulkMembers.push(name);
            document.getElementById(`bulk-check-${name}`).innerText = '✅';
        }
    });
    updateBulkCount();
}

function clearSelection() {
    selectedBulkMembers = [];
    document.querySelectorAll('.selectable-member span').forEach(s => s.innerText = '⬜');
    updateBulkCount();
}

async function sendBulkPraise() {
    const reason = document.getElementById('bulk-praise-reason').value.trim();
    const eventName = document.getElementById('bulk-event-name').value.trim() || 'Ивент';

    if (selectedBulkMembers.length === 0 || !reason) {
        tg.showAlert('Выберите участников и введите причину');
        return;
    }

    try {
        const response = await fetch(`/api/bulk_praise?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                members: selectedBulkMembers,
                reason,
                event_name: eventName
            })
        });

        const data = await response.json();
        if (response.ok) {
            tg.showAlert(data.message);
            navigate('admin');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка: ' + error.message);
    }
}

// =========================
// 📋 ИСТОРИЯ УЧАСТНИКА
// =========================
async function showMemberHistoryPage(member) {
    currentHistoryMember = member;
    document.getElementById('member-history-title').innerText = `📋 ${member}`;
    showPage('member-history-page');
    showMemberHistory('praise');
}

async function showMemberHistory(type) {
    try {
        const endpoint = type === 'praise'
            ? `/api/member_praises/${currentHistoryMember}?user_id=${currentUser.id}`
            : `/api/member_preds/${currentHistoryMember}?user_id=${currentUser.id}`;

        const response = await fetch(endpoint);
        const data = await response.json();

        const items = type === 'praise' ? data.praises : data.preds;

        if (items.length === 0) {
            document.getElementById('member-history-data').innerHTML = '<p>📭 Нет записей</p>';
        } else {
            document.getElementById('member-history-data').innerHTML = items.map(item => `
                <div class="card">
                    ${type === 'praise' ? `<p>👤 От: ${item.from}</p>` : ''}
                    <p>📝 ${item.reason}</p>
                    <p>🕒 ${item.date}</p>
                </div>
            `).join('');
        }
    } catch (error) {
        document.getElementById('member-history-data').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

// =========================
// 🎖 СМЕНА РАЗРЯДА
// =========================
async function showChangeRolePage(member) {
    currentRoleChangeMember = member;
    document.getElementById('change-role-member').innerText = `Участник: ${member}`;

    try {
        const response = await fetch('/api/available_roles');
        const data = await response.json();

        document.getElementById('new-role-select').innerHTML = data.roles
            .map(r => `<option value="${r}">${r}</option>`).join('');

        showPage('change-role-page');
    } catch (error) {
        tg.showAlert('Ошибка загрузки разрядов');
    }
}

async function confirmChangeRole() {
    const newRole = document.getElementById('new-role-select').value;

    try {
        const response = await fetch(`/api/change_role?user_id=${currentUser.id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({member: currentRoleChangeMember, role: newRole})
        });

        const data = await response.json();
        if (response.ok) {
            tg.showAlert(data.message);
            navigate('clan_list');
        } else {
            tg.showAlert('Ошибка: ' + data.detail);
        }
    } catch (error) {
        tg.showAlert('Ошибка: ' + error.message);
    }
}

// Запуск
init();