const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentUser = null;
let isAdmin = false;
let isRegistered = false;
let userNickname = null;

// Инициализация
async function init() {
    try {
        const initData = tg.initData || '';

        // Если initData пустой (тестирование в браузере)
        if (!initData) {
            tg.showAlert('⚠️ Mini App работает только внутри Telegram!\n\nОткройте через бота @petclanbot');
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
        isRegistered = data.is_registered;
        userNickname = data.nickname;

        // Настройка темы Telegram
        tg.MainButton.setParams({color: tg.themeParams.button_color || '#3390ec'});
        tg.setHeaderColor(tg.themeParams.bg_color || '#1a1a2e');

        showPage('home-page');
        renderUserInfo();

        if (isAdmin) {
            document.getElementById('admin-btn').style.display = 'block';
        }

        // Анимация появления
        document.body.classList.add('loaded');

    } catch (error) {
        console.error('Auth error:', error);
        tg.showAlert(`❌ Ошибка авторизации:\n${error.message}\n\nПопробуйте перезапустить бота.`);
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

// Выбор участника
function selectMember(member) {
    selectedMember = member;
    document.getElementById('member-actions-title').innerText = `Действия: ${member}`;
    document.getElementById('member-info-display').innerHTML = `<div class="card">👤 <b>${member}</b></div>`;

    if (isAdmin) {
        document.getElementById('admin-actions').style.display = 'block';
    } else {
        document.getElementById('admin-actions').style.display = 'none';
    }

    // Очистка полей
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

// Админ меню
function renderAdminMenu() {
    document.getElementById('admin-data').innerHTML = '<div class="card">Выберите раздел выше</div>';
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

// Запуск
init();