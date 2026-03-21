const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentUser = null;
let isAdmin = false;
let isTechAdmin = false;
let isRegistered = false;
let userNickname = null;
let selectedMember = null;
let selectedBulkMembers = [];
let currentHistoryMember = null;
let currentRoleChangeMember = null;

// =========================
// 🚀 ИНИЦИАЛИЗАЦИЯ
// =========================
async function init() {
    try {
        const initData = tg.initData || '';

        if (!initData) {
            tg.showAlert('⚠️ Mini App работает только внутри Telegram!\n\nОткройте через бота');
            return;
        }

        const response = await fetch('/api/auth', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({initData})
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({detail: 'Unknown error'}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        currentUser = data.user;
        isAdmin = data.is_admin;
        isTechAdmin = data.is_tech_admin;
        isRegistered = data.is_registered;
        userNickname = data.nickname;

        tg.MainButton.setParams({color: tg.themeParams.button_color || '#3390ec'});
        tg.setHeaderColor(tg.themeParams.bg_color || '#1a1a2e');

        showPage('home-page');
        renderUserInfo();

        if (isAdmin || isTechAdmin) {
            document.getElementById('admin-btn').style.display = 'block';
        }

        document.body.classList.add('loaded');

    } catch (error) {
        console.error('Auth error:', error);
        tg.showAlert(`❌ Ошибка авторизации:\n${error.message}`);
    }
}

// =========================
// 🧭 НАВИГАЦИЯ
// =========================
function navigate(page) {
    showPage(page + '-page');

    if (page === 'profile' && isRegistered) {
        loadProfile();
    } else if (page === 'clan_list') {
        loadClanList();
    } else if (page === 'stats') {
        loadStats('week');
    } else if (page === 'admin' && (isAdmin || isTechAdmin)) {
        renderAdminMenu();
    } else if (page === 'notifications') {
        loadNotifications();
    } else if (page === 'devlogs') {
        loadDevlogs();
    }
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(pageId);
    if (page) {
        page.classList.add('active');
    }
}

// =========================
// 👤 ПРОФИЛЬ
// =========================
function renderUserInfo() {
    const userInfo = document.getElementById('user-info');
    if (!userInfo) return;

    userInfo.innerHTML = `
        <p>👤 <strong>${currentUser.first_name} ${currentUser.last_name || ''}</strong></p>
        <p>@${currentUser.username || 'Нет username'}</p>
        <p>${isRegistered ? '✅ Зарегистрирован' : '⏳ Не зарегистрирован'}</p>
        ${userNickname ? `<p>🎮 Ник: <strong>${userNickname}</strong></p>` : ''}
        ${isAdmin ? '<p>🛡 <strong>Администратор</strong></p>' : ''}
        ${isTechAdmin && !isAdmin ? '<p>🔧 <strong>Тех Админ</strong></p>' : ''}
    `;
}

async function loadProfile() {
    try {
        const response = await fetch(`/api/profile/${currentUser.id}`);
        const data = await response.json();

        document.getElementById('profile-data').innerHTML = `
            <p>🎮 <strong>${data.nick}</strong></p>
            <p>🆔 ${data.steam_id}</p>
            <p>🎖 Роль: ${data.role}</p>
            <p>⚠️ Предупреждения: ${data.warns}</p>
            <p>👏 Похвалы: ${data.praises}</p>
            <p>📊 Рейтинг: ${data.score}</p>
            <p>📌 Статус: ${data.desirable}</p>
        `;
    } catch (error) {
        document.getElementById('profile-data').innerHTML = '<p class="error-message">❌ Ошибка загрузки профиля</p>';
    }
}

// =========================
// 📋 СПИСОК КЛАНА (🔥 ИСПРАВЛЕНО)
// =========================
async function loadClanList() {
    try {
        const response = await fetch('/api/clan_members');
        const data = await response.json();

        if (!data.members || data.members.length === 0) {
            document.getElementById('clan-members').innerHTML = '<p class="empty-message">📭 Список пуст</p>';
            return;
        }

        // 🔥 ИСПРАВЛЕНИЕ: добавляем onclick для каждого участника
        document.getElementById('clan-members').innerHTML = data.members
            .map(m => `
                <div class="member-item" onclick="selectMember('${m.replace(/'/g, "\\'")}')">
                    <span class="member-name">👤 ${m}</span>
                    <span class="member-arrow">›</span>
                </div>
            `)
            .join('');
    } catch (error) {
        document.getElementById('clan-members').innerHTML = '<p class="error-message">❌ Ошибка загрузки</p>';
    }
}

function selectMember(member) {
    selectedMember = member;
    document.getElementById('member-actions-title').innerText = `Действия: ${member}`;
    document.getElementById('member-info-display').innerHTML = `<p>👤 <strong>${member}</strong></p>`;

    if (isAdmin) {
        document.getElementById('admin-actions').style.display = 'block';
    } else {
        document.getElementById('admin-actions').style.display = 'none';
    }

    document.getElementById('praise-reason').value = '';
    document.getElementById('complaint-reason').value = '';
    document.getElementById('pred-reason').value = '';

    showPage('member_actions-page');
}

// =========================
// 👏 ПОХВАЛА
// =========================
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

// =========================
// ⚖ ЖАЛОБА
// =========================
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

// =========================
// ⚠ ПРЕДУПРЕЖДЕНИЕ
// =========================
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

// =========================
// 📊 СТАТИСТИКА
// =========================
async function loadStats(period) {
    try {
        const response = await fetch(`/api/stats/${period}`);
        const data = await response.json();

        if (data.top.length === 0) {
            document.getElementById('stats-data').innerHTML = '<p class="empty-message">📭 Пока нет похвал</p>';
        } else {
            document.getElementById('stats-data').innerHTML = data.top
                .map((t, i) => `<p><strong>${i+1}. ${t.nick}</strong> — ${t.count} 👏</p>`)
                .join('');
        }
    } catch (error) {
        document.getElementById('stats-data').innerHTML = '<p class="error-message">❌ Ошибка загрузки</p>';
    }
}

// =========================
// 🛡 АДМИН МЕНЮ (🔥 ОБНОВЛЕНО)
// =========================
function renderAdminMenu() {
    let techAdminButtons = '';
    if (isTechAdmin) {
        techAdminButtons = `
            <button class="btn btn-primary" onclick="loadNotifications()">📢 Оповещения</button>
            <button class="btn btn-primary" onclick="loadDevlogs()">📝 Devlogs</button>
        `;
    }

    let adminButtons = '';
    if (isAdmin) {
        adminButtons = `
            <button class="btn btn-primary" onclick="showBulkPraise()">🏆 Массовая похвала</button>
            <button class="btn" onclick="loadComplaints()">⚖ Жалобы</button>
        `;
    }

    document.getElementById('admin-data').innerHTML = `
        ${techAdminButtons}
        ${adminButtons}
        <button class="btn" onclick="loadLogs()">📝 Логи</button>
        <button class="btn" onclick="loadApplications()">📬 Заявки</button>
    `;
}

// =========================
// 📢 ОПОВЕЩЕНИЯ
// =========================
function toggleScheduleTime() {
    const schedule = document.getElementById('notification-schedule').value;
    const container = document.getElementById('schedule-time-container');
    if (container) {
        container.style.display = schedule === 'schedule' ? 'block' : 'none';
    }
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
            body: JSON.stringify({audience, text, schedule_time: scheduleTime})
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

        if (!data.notifications || data.notifications.length === 0) {
            document.getElementById('notifications-list').innerHTML = '<p class="empty-message">📭 Нет оповещений</p>';
        } else {
            document.getElementById('notifications-list').innerHTML = data.notifications
                .reverse()
                .map(n => `
                    <div class="card notification-card">
                        <p><strong>📢 ${n.audience}</strong></p>
                        <p>${n.text}</p>
                        <p><small>👤 ${n.author} | 🕒 ${n.created} | 📅 ${n.schedule}</small></p>
                        <p><span class="status-badge status-${n.status === 'отправлено' ? 'success' : 'warning'}">${n.status}</span></p>
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

        if (!data.devlogs || data.devlogs.length === 0) {
            document.getElementById('devlogs-list').innerHTML = '<p class="empty-message">📭 Нет devlogs</p>';
        } else {
            document.getElementById('devlogs-list').innerHTML = data.devlogs
                .reverse()
                .map(d => `
                    <div class="card devlog-card">
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

        if (!data.members || data.members.length === 0) {
            document.getElementById('bulk-members-list').innerHTML = '<p class="empty-message">📭 Нет участников</p>';
            return;
        }

        document.getElementById('bulk-members-list').innerHTML = data.members
            .map(m => `
                <div class="card selectable-member" onclick="toggleBulkSelect('${m.replace(/'/g, "\\'")}')">
                    <span class="checkbox" id="bulk-check-${m.replace(/'/g, '\\-')}">⬜</span>
                    <span class="member-name">${m}</span>
                </div>
            `).join('');
    } catch (error) {
        document.getElementById('bulk-members-list').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

function toggleBulkSelect(member) {
    const safeId = member.replace(/'/g, '\\-');
    const index = selectedBulkMembers.indexOf(member);
    const checkbox = document.getElementById(`bulk-check-${safeId}`);

    if (!checkbox) return;

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
    const countEl = document.getElementById('bulk-selected-count');
    if (countEl) {
        countEl.innerText = `Выбрано: ${selectedBulkMembers.length}`;
    }
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
            body: JSON.stringify({members: selectedBulkMembers, reason, event_name: eventName})
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
    const titleEl = document.getElementById('member-history-title');
    if (titleEl) {
        titleEl.innerText = `📋 ${member}`;
    }
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

        if (!items || items.length === 0) {
            document.getElementById('member-history-data').innerHTML = '<p class="empty-message">📭 Нет записей</p>';
        } else {
            document.getElementById('member-history-data').innerHTML = items.map(item => `
                <div class="card history-item">
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
    const memberEl = document.getElementById('change-role-member');
    if (memberEl) {
        memberEl.innerText = `Участник: ${member}`;
    }

    try {
        const response = await fetch('/api/available_roles');
        const data = await response.json();

        const select = document.getElementById('new-role-select');
        if (select && data.roles) {
            select.innerHTML = data.roles.map(r => `<option value="${r}">${r}</option>`).join('');
        }

        showPage('change-role-page');
    } catch (error) {
        tg.showAlert('Ошибка загрузки разрядов');
    }
}

async function confirmChangeRole() {
    const select = document.getElementById('new-role-select');
    if (!select) return;

    const newRole = select.value;

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

// =========================
// 📬 ЗАЯВКИ
// =========================
async function loadApplications() {
    showPage('applications-page');
    try {
        const response = await fetch(`/api/applications?user_id=${currentUser.id}`);
        const data = await response.json();

        if (!data.applications || data.applications.length === 0) {
            document.getElementById('applications-data').innerHTML = '<p class="empty-message">📭 Нет заявок</p>';
        } else {
            document.getElementById('applications-data').innerHTML = data.applications
                .map(a => `
                    <div class="card">
                        <p><strong>📬 #${a.id}</strong> | ${a.nick}</p>
                        <p>🆔 ${a.steam_id}</p>
                        <p>👤 ${a.tg_username}</p>
                        <p>🕒 ${a.date}</p>
                        <p><span class="status-badge">${a.status}</span></p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('applications-data').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

// =========================
// 📝 ЛОГИ
// =========================
async function loadLogs() {
    showPage('logs-page');
    try {
        const response = await fetch(`/api/logs?user_id=${currentUser.id}`);
        const data = await response.json();

        if (!data.logs || data.logs.length === 0) {
            document.getElementById('logs-data').innerHTML = '<p class="empty-message">📭 Логи пусты</p>';
        } else {
            document.getElementById('logs-data').innerHTML = data.logs
                .map(l => `
                    <div class="card log-item">
                        <p><strong>${l[4] || 'N/A'}</strong></p>
                        <p>${l[0] || '?'} | ${l[1] || '?'} → ${l[3] || '?'}</p>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('logs-data').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

// =========================
// ⚖ ЖАЛОБЫ
// =========================
async function loadComplaints() {
    showPage('complaints-page');
    try {
        const response = await fetch(`/api/complaints?user_id=${currentUser.id}`);
        const data = await response.json();

        if (!data.complaints || data.complaints.length === 0) {
            document.getElementById('complaints-data').innerHTML = '<p class="empty-message">📭 Нет активных жалоб</p>';
        } else {
            document.getElementById('complaints-data').innerHTML = data.complaints
                .map(c => `
                    <div class="card complaint-card">
                        <p><strong>⚖ Жалоба #${c.index}</strong></p>
                        <p>👤 От: ${c.from_user}</p>
                        <p>🎯 На: ${c.to_member}</p>
                        <p>📝 ${c.reason}</p>
                        <p>🕒 ${c.date}</p>
                        <p><span class="status-badge">${c.status}</span></p>
                        <div class="action-buttons">
                            <button class="btn btn-warning" onclick="closeComplaint(${c.index}, 'pred')">⚠ Пред + закрыть</button>
                            <button class="btn" onclick="closeComplaint(${c.index}, 'noaction')">❌ Закрыть</button>
                        </div>
                    </div>
                `).join('');
        }
    } catch (error) {
        document.getElementById('complaints-data').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}

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

// =========================
// 🎖 РАЗРЯДЫ
// =========================
async function loadRoles() {
    showPage('roles-page');
    try {
        const response = await fetch('/api/roles');
        const data = await response.json();

        document.getElementById('roles-data').innerHTML = `
            <h3>🪖 Сквадные (${data.сквадной?.length || 0})</h3>
            <p>${data.сквадной?.join(', ') || 'Нет'}</p>
            <h3>🎯 Пехи (${data.пех?.length || 0})</h3>
            <p>${data.пех?.join(', ') || 'Нет'}</p>
            <h3>🔧 Техи (${data.тех?.length || 0})</h3>
            <p>${data.тех?.join(', ') || 'Нет'}</p>
        `;
    } catch (error) {
        document.getElementById('roles-data').innerHTML = '<p class="error-message">❌ Ошибка</p>';
    }
}
// ============ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ============
let currentViewedMember = null;
let currentRecordTab = 'praises';

// ============ ОТКРЫТИЕ МОДАЛЬНОГО ОКНА ============
async function openMemberRecordsModal(nickname, type = 'praises') {
    currentViewedMember = nickname;
    currentRecordTab = type;

    const modal = document.getElementById('member-records-modal');
    const title = document.getElementById('modal-title');
    const list = document.getElementById('member-records-list');
    const empty = document.getElementById('member-records-empty');

    title.textContent = `📋 Записи: @${nickname}`;
    list.innerHTML = '<div class="loading-spinner"></div>';
    empty.style.display = 'none';
    modal.classList.add('active');

    // Обновляем активный таб
    document.querySelectorAll('#member-records-modal .admin-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === type);
    });

    // Загружаем данные
    await loadMemberRecords(nickname, type);
}

// ============ ЗАКРЫТИЕ МОДАЛЬНОГО ОКНА ============
function closeMemberRecordsModal() {
    const modal = document.getElementById('member-records-modal');
    modal.classList.remove('active');
    currentViewedMember = null;
}

// ============ ПЕРЕКЛЮЧЕНИЕ ТАБОВ ============
function switchMemberRecordTab(type) {
    if (!currentViewedMember) return;

    currentRecordTab = type;
    document.querySelectorAll('#member-records-modal .admin-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === type);
    });
    loadMemberRecords(currentViewedMember, type);
}

// ============ ЗАГРУЗКА ЗАПИСЕЙ УЧАСТНИКА ============
async function loadMemberRecords(nickname, type) {
    const list = document.getElementById('member-records-list');
    const empty = document.getElementById('member-records-empty');
    const endpoint = type === 'praises' ? 'praises' : 'preds';

    list.innerHTML = '<div class="loading-spinner"></div>';
    empty.style.display = 'none';

    try {
        const response = await fetch(`/api/member/${encodeURIComponent(nickname)}/${endpoint}?user_id=${currentUser.id}`);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Ошибка загрузки');
        }

        const result = await response.json();

        if (!result.data || result.data.length === 0) {
            list.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        // Сортировка: новые сверху
        result.data.sort((a, b) => b.row_index - a.row_index);

        list.innerHTML = result.data.map(record => {
            const isPraise = type === 'praises';
            const typeClass = isPraise ? 'praise' : 'pred';
            const typeLabel = isPraise ? '👏 ПОХВАЛА' : '⚠️ ПРЕДУПРЕЖДЕНИЕ';
            const deleteEndpoint = isPraise ? 'praise' : 'pred';

            return `
                <div class="record-item ${typeClass}">
                    <div class="record-header">
                        <span class="record-type">${typeLabel}</span>
                        ${isAdmin() ? `<button class="btn-delete" onclick="deleteMemberRecord('${nickname}', '${deleteEndpoint}', ${record.row_index})">🗑️</button>` : ''}
                    </div>
                    <div class="record-from">От: @${escapeHtml(record.from)}</div>
                    <div class="record-reason">${escapeHtml(record.reason)}</div>
                    ${record.date ? `<div class="record-date">📅 ${escapeHtml(record.date)}</div>` : ''}
                </div>
            `;
        }).join('');

    } catch (error) {
        list.innerHTML = `<div class="error-message">❌ ${error.message}</div>`;
        console.error('Load member records error:', error);
    }
}

// ============ УДАЛЕНИЕ ЗАПИСИ УЧАСТНИКА ============
async function deleteMemberRecord(nickname, type, rowIndex) {
    const typeName = type === 'praise' ? 'похвалу' : 'предупреждение';

    if (!confirm(`⚠️ Удалить эту ${typeName} для @${nickname}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/admin/${type}/${encodeURIComponent(nickname)}/${rowIndex}?user_id=${currentUser.id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok) {
            tg.showAlert(result.message || 'Запись удалена ✅');
            // Перезагружаем список
            loadMemberRecords(nickname, currentRecordTab);
        } else {
            throw new Error(result.detail || 'Ошибка удаления');
        }
    } catch (error) {
        tg.showAlert('❌ ' + error.message);
        console.error('Delete member record error:', error);
    }
}

// ============ ПРОВЕРКА: АДМИН ============
function isAdmin() {
    return currentUser?.id && ADMIN_IDS.includes(currentUser.id);
}

// ============ ВСПОМОГАТЕЛЬНАЯ: ЭКРАНИРОВАНИЕ ============
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ ЗАКРЫТИЕ МОДАЛКИ ПО КЛИКУ ВНЕ ============
document.addEventListener('click', (e) => {
    const modal = document.getElementById('member-records-modal');
    if (e.target === modal) {
        closeMemberRecordsModal();
    }
});
// =========================
// 🚀 ЗАПУСК
// =========================
init();