import logging
from datetime import datetime, timedelta
import os
import json
import re

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Для планировщика
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# =========================
# 🔐 ENV
# =========================

TOKEN = os.getenv("TOKEN")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID")
REPORT_TOPIC_ID = os.getenv("REPORT_TOPIC_ID")
GROUP_LINK = os.getenv("GROUP_LINK")  # Ссылка на группу

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_data = json.loads(os.getenv("CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_KEY)


# =========================
# 📊 Google Sheets
# =========================

def get_clan_members():
    ws = sheet.worksheet("участники клана")
    return [v for v in ws.col_values(1) if v.strip()]


# ---------- ИНФОРМАЦИЯ ОБ УЧАСТНИКЕ ----------
def get_member_info(nickname):
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 1 and row[0].strip() == nickname.strip():
            return {
                'nick': row[0] if len(row) > 0 else 'N/A',
                'steam_id': row[1] if len(row) > 1 else 'N/A',
                'role': row[2] if len(row) > 2 else 'N/A',
                'warns': row[3] if len(row) > 3 else '0',
                'praises': row[4] if len(row) > 4 else '0',
                'score': row[5] if len(row) > 5 else '0',
                'desirable': row[6] if len(row) > 6 else 'N/A',
                'tg_username': row[7] if len(row) > 7 else '',
                'tg_id': row[8] if len(row) > 8 else ''
            }
    return None


def find_member_by_tg_id(tg_id):
    """Ищет участника по Telegram ID"""
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 9 and row[8].strip() == str(tg_id):
            return row[0]
    return None


def update_member_tg_data(nickname, tg_username, tg_id):
    """Обновляет TG данные участника"""
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for idx, row in enumerate(rows[1:], start=2):
        if row[0].strip() == nickname.strip():
            ws.update_cell(idx, 8, tg_username)
            ws.update_cell(idx, 9, str(tg_id))
            return True
    return False


def add_new_member(nickname, steam_id, tg_username, tg_id):
    """Добавляет нового участника в таблицу"""
    ws = sheet.worksheet("участники клана")

    # Проверяем дубликаты
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 2 and row[1].strip() == steam_id.strip():
            logging.warning(f"⚠️ Участник {nickname} уже существует (по Steam ID)")
            return False
        if len(row) >= 9 and row[8].strip() == str(tg_id).strip():
            logging.warning(f"⚠️ Участник {nickname} уже существует (по TG ID)")
            return False

    ws.append_row([
        nickname,
        steam_id,
        "новичок",
        "0",
        "0",
        "0",
        "желателен",
        tg_username,
        str(tg_id)
    ])
    logging.info(f"✅ Участник {nickname} добавлен в таблицу")
    return True


# ---------- ЗАЯВКИ НА ВСТУПЛЕНИЕ ----------
def get_applications_sheet():
    try:
        return sheet.worksheet("Заявки на вступление")
    except:
        ws = sheet.add_worksheet("Заявки на вступление", rows=100, cols=7)
        ws.append_row(["ID", "Никнейм", "Steam ID", "TG Username", "TG ID", "Дата", "Статус"])
        return ws


def add_application(nickname, steam_id, tg_username, tg_id):
    ws = get_applications_sheet()
    rows = ws.get_all_values()
    new_id = str(max([int(r[0]) for r in rows[1:] if r[0].isdigit()], default=0) + 1)
    date = datetime.now().strftime("%d.%m.%Y %H:%M")
    ws.append_row([new_id, nickname, steam_id, tg_username, str(tg_id), date, "ожидает"])
    return new_id


def get_applications(status=None):
    ws = get_applications_sheet()
    rows = ws.get_all_values()[1:]
    if status:
        return [row for row in rows if len(row) >= 7 and row[6] == status]
    return [row for row in rows if len(row) >= 7]


def update_application_status(app_id, new_status):
    ws = get_applications_sheet()
    rows = ws.get_all_values()
    for idx, row in enumerate(rows[1:], start=2):
        if row[0] == app_id:
            ws.update_cell(idx, 7, new_status)
            return True
    return False


def get_application_by_id(app_id):
    ws = get_applications_sheet()
    rows = ws.get_all_values()[1:]
    for row in rows:
        if row[0] == app_id:
            return {
                'id': row[0],
                'nick': row[1],
                'steam_id': row[2],
                'tg_username': row[3],
                'tg_id': row[4],
                'date': row[5],
                'status': row[6] if len(row) > 6 else 'ожидает'
            }
    return None


# ---------- ПРЕД ----------
def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, reason, date])


# ---------- ПОХВАЛА ----------
def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, from_user, reason, date])


# ---------- ЛОГИ ----------
def append_log(action, username, user_id, to_member):
    ws = sheet.worksheet("логи")
    date = datetime.now().strftime("%d.%m.%Y %H:%M")
    ws.append_row([action, username, user_id, to_member, date])


def get_logs():
    ws = sheet.worksheet("логи")
    return ws.get_all_values()


def clear_logs():
    ws = sheet.worksheet("логи")
    ws.clear()
    ws.append_row(["Тип", "Username", "UserID", "Кому", "Дата"])


# ---------- РАЗРЯДЫ ----------
def get_roles_sheet():
    return sheet.worksheet("разряды")


def get_roles_data():
    return get_roles_sheet().get_all_values()[1:]


def get_members_by_role(role):
    return [r[0] for r in get_roles_data() if r[1].lower() == role]


def count_by_role(role):
    return len(get_members_by_role(role))


def update_role(member, new_role):
    ws = get_roles_sheet()
    rows = ws.get_all_values()
    for idx, row in enumerate(rows):
        if row and row[0] == member:
            ws.update_cell(idx + 1, 2, new_role)
            break


# ---------- СТАТИСТИКА ----------
def get_top_praises(weeks=None):
    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()[1:]
    counter = {}
    for row in rows:
        try:
            if len(row) < 4 or not row[0].strip():
                continue
            member = row[0].strip()
            if weeks is not None:
                date_str = row[3].strip() if len(row) > 3 and row[3].strip() else None
                if not date_str:
                    continue
                date = datetime.strptime(date_str, "%d.%m.%Y")
                if date < datetime.now() - timedelta(weeks=weeks):
                    continue
            counter[member] = counter.get(member, 0) + 1
        except Exception:
            continue
    return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:10]


# ---------- ШАБЛОНЫ ОТЧЁТОВ ----------
def get_templates_sheet():
    try:
        return sheet.worksheet("Шаблоны отчётов")
    except:
        ws = sheet.add_worksheet("Шаблоны отчётов", rows=100, cols=4)
        ws.append_row(["ID", "Название", "Текст шаблона", "Активен"])
        ws.append_row(["1", "Стандарт", "🏆 Итоги недели!\n\n{top_list}\n\nТак держать! 💪", "да"])
        return ws


def get_report_templates():
    ws = get_templates_sheet()
    rows = ws.get_all_values()[1:]
    return [
        {"id": row[0], "name": row[1], "text": row[2], "active": row[3].lower() == "да"}
        for row in rows if len(row) >= 4 and row[0].strip()
    ]


def get_active_template():
    templates = get_report_templates()
    active = [t for t in templates if t["active"]]
    return active[0] if active else None


def update_template(template_id, field, value):
    ws = get_templates_sheet()
    rows = ws.get_all_values()
    for idx, row in enumerate(rows[1:], start=2):
        if row[0] == template_id:
            col = {"name": 2, "text": 3, "active": 4}.get(field)
            if col:
                ws.update_cell(idx, col, value)
            return True
    return False


def add_template(name, text):
    ws = get_templates_sheet()
    rows = ws.get_all_values()
    new_id = str(max([int(r[0]) for r in rows[1:] if r[0].isdigit()], default=0) + 1)
    ws.append_row([new_id, name, text, "нет"])
    return new_id


# ---------- ГЕНЕРАЦИЯ ОТЧЁТА ----------
def generate_weekly_report():
    top = get_top_praises(weeks=1)
    template = get_active_template()

    if not template:
        return "❌ Не найден активный шаблон отчёта"

    if not top:
        top_text = "📭 На этой неделе похвал ещё нет. Давайте активнее! 🔥"
    else:
        top_text = "\n".join(
            f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1)
        )

    report = template["text"].format(
        top_list=top_text,
        date=datetime.now().strftime("%d.%m.%Y"),
        week_start=(datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")
    )

    return report


# ---------- ОТПРАВКА ОТЧЁТА ----------
async def send_weekly_report():
    if not REPORT_CHAT_ID:
        logging.warning("REPORT_CHAT_ID не задан — отчёт не отправлен")
        return

    report_text = generate_weekly_report()

    try:
        if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
            await bot.send_message(
                chat_id=REPORT_CHAT_ID,
                text=report_text,
                parse_mode="HTML",
                message_thread_id=int(REPORT_TOPIC_ID)
            )
        else:
            await bot.send_message(
                chat_id=REPORT_CHAT_ID,
                text=report_text,
                parse_mode="HTML"
            )
        logging.info("✅ Еженедельный отчёт отправлен")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки отчёта: {e}")


# ---------- ЖАЛОБЫ ----------
def add_complaint(from_user, from_user_id, to_member, reason):
    ws = sheet.worksheet("жалобы")
    date = datetime.now().strftime("%d.%m.%Y %H:%M")
    ws.append_row([from_user, str(from_user_id), to_member, reason, date, "активна", "", ""])


def get_complaints():
    ws = sheet.worksheet("жалобы")
    return ws.get_all_values()


def update_complaint_field(index, column, value):
    ws = sheet.worksheet("жалобы")
    ws.update_cell(index + 2, column, value)


def close_complaint(index, closed_by=None):
    update_complaint_field(index, 6, "закрыта")
    if closed_by:
        try:
            ws = sheet.worksheet("жалобы")
            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            ws.update_cell(index + 2, 8, f"{closed_by} | {timestamp}")
        except:
            pass


def add_proof_to_complaint(index, proof_text):
    ws = sheet.worksheet("жалобы")
    current = ws.cell(index + 2, 7).value or ""
    new_proof = f"{current}\n{proof_text}" if current else proof_text
    ws.update_cell(index + 2, 7, new_proof)


# =========================
# 🤖 INIT
# =========================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


# =========================
# MENU
# =========================

def main_menu(user_id, is_registered=False, has_pending_app=False):
    keyboard = InlineKeyboardMarkup()

    if is_registered:
        keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
        keyboard.add(InlineKeyboardButton("📊 Статистика", callback_data="stats"))
        keyboard.add(InlineKeyboardButton("⚖ Жалобы", callback_data="complaints"))
        keyboard.add(InlineKeyboardButton("👤 Мой профиль", callback_data="my_profile"))
    else:
        keyboard.add(InlineKeyboardButton("📝 Подать заявку", callback_data="apply_start"))
        if has_pending_app:
            keyboard.add(InlineKeyboardButton("📋 Статус заявки", callback_data="app_status"))

    if user_id in ADMINS:
        keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
        keyboard.add(InlineKeyboardButton("📝 Логи", callback_data="logs"))
        keyboard.add(InlineKeyboardButton("📄 Шаблоны отчётов", callback_data="templates_menu"))
        keyboard.add(InlineKeyboardButton("📬 Заявки на вступление", callback_data="applications_menu"))

    return keyboard


# =========================
# FSM
# =========================

class ActionState(StatesGroup):
    waiting_reason = State()
    waiting_proof = State()
    editing_template = State()
    new_template_name = State()
    new_template_text = State()
    # Регистрация и заявки
    reg_rules = State()
    reg_steam_nick = State()
    reg_steam_id = State()
    reg_confirm = State()


# =========================
# START / CANCEL / BACK
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    existing_nick = find_member_by_tg_id(user_id)

    if existing_nick:
        await message.answer(
            f"👋 <b>С возвращением, {username}!</b>\n\n"
            f"✅ Вы уже зарегистрированы как <b>{existing_nick}</b>",
            reply_markup=main_menu(user_id, is_registered=True),
            parse_mode="HTML"
        )
    else:
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)

        await state.update_data(tg_username=username, tg_id=user_id)

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("📝 Подать заявку на вступление", callback_data="apply_start"))

        if has_pending:
            keyboard.add(InlineKeyboardButton("📋 Проверить статус заявки", callback_data="app_status"))

        await message.answer(
            f"👋 <b>Привет, {username}!</b>\n\n"
            f"Добро пожаловать в бот клана <b>PET</b>!\n\n"
            f"Чтобы вступить в клан, вам нужно:\n"
            f"1️⃣ Подать заявку\n"
            f"2️⃣ Дождаться проверки модераторами\n"
            f"3️⃣ Получить ссылку на группу\n\n"
            f"<b>Готовы начать?</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    existing_nick = find_member_by_tg_id(user_id)
    apps = get_applications(status="ожидает")
    has_pending = any(app[4] == str(user_id) for app in apps)

    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending)
    )


@dp.message_handler(state='*', commands=['cancel'])
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.answer("✅ Действие отменено", reply_markup=main_menu(message.from_user.id))


# =========================
# 📝 ЗАЯВКИ НА ВСТУПЛЕНИЕ
# =========================

@dp.callback_query_handler(lambda c: c.data == "apply_start")
async def apply_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    apps = get_applications(status="ожидает")
    if any(app[4] == str(user_id) for app in apps):
        await callback.answer("⚠️ У вас уже есть активная заявка!", show_alert=True)
        return

    await state.update_data(tg_username=callback.from_user.username or callback.from_user.full_name, tg_id=user_id)
    await ActionState.reg_rules.set()

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Я согласен с правилами", callback_data="rules_accept"),
        InlineKeyboardButton("❌ Отмена", callback_data="back_menu")
    )

    await callback.message.edit_text(
        "📜 <b>Правила клана PET</b>\n\n"
        "1️⃣ Уважительное отношение ко всем участникам\n"
        "2️⃣ Запрет на читы и стороннее ПО\n"
        "3️⃣ Активное участие в жизни клана\n"
        "4️⃣ Выполнение приказов руководства\n"
        "5️⃣ Запрет на разглашение информации клана\n\n"
        "⚠️ Нарушение правил ведёт к предупреждению или исключению!\n\n"
        "<b>Вы согласны соблюдать правила?</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "rules_accept")
async def rules_accepted(callback: types.CallbackQuery, state: FSMContext):
    await ActionState.reg_steam_nick.set()
    await callback.message.edit_text(
        "🆕 <b>Регистрация заявки</b>\n\n"
        "Введите ваш <b>никнейм в Steam</b> (как в игре):\n\n"
        "<i>Пример: [PET] КИРЮХА</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message_handler(state=ActionState.reg_steam_nick)
async def reg_save_steam_nick(message: types.Message, state: FSMContext):
    await state.update_data(steam_nick=message.text.strip())
    await ActionState.reg_steam_id.set()
    await message.answer(
        "🎮 Теперь введите ваш <b>Steam ID</b> (64-bit):\n\n"
        "<i>Пример: 76561198984240881</i>\n\n"
        "Как узнать: https://steamid.io/",
        parse_mode="HTML"
    )


@dp.message_handler(state=ActionState.reg_steam_id)
async def reg_save_steam_id(message: types.Message, state: FSMContext):
    steam_id = message.text.strip()

    if not steam_id.isdigit() or len(steam_id) < 17:
        await message.answer("❌ Неверный формат Steam ID. Попробуйте ещё раз:")
        return

    await state.update_data(steam_id=steam_id)
    await ActionState.reg_confirm.set()

    data = await state.get_data()
    steam_nick = data.get("steam_nick")

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить и отправить заявку", callback_data="app_submit"),
        InlineKeyboardButton("❌ Изменить данные", callback_data="apply_start")
    )

    await message.answer(
        f"📋 <b>Проверьте данные заявки:</b>\n\n"
        f"🎮 Steam Nick: <code>{steam_nick}</code>\n"
        f"🆔 Steam ID: <code>{steam_id}</code>\n"
        f"👤 TG: <code>{message.from_user.full_name}</code>\n\n"
        f"После отправки модераторы проверят вашу заявку!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query_handler(lambda c: c.data == "app_submit")
async def app_submit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    steam_nick = data.get("steam_nick")
    steam_id = data.get("steam_id")
    tg_username = data.get("tg_username")
    tg_id = data.get("tg_id")

    if not all([steam_nick, steam_id, tg_id]):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    app_id = add_application(steam_nick, steam_id, tg_username, tg_id)
    append_log("ЗАЯВКА_НА_ВСТУПЛЕНИЕ", tg_username, tg_id, steam_nick)

    await state.finish()

    for admin_id in ADMINS:
        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
            )
            await bot.send_message(
                admin_id,
                f"📬 <b>Новая заявка на вступление!</b>\n\n"
                f"🆔 <b>ID заявки:</b> #{app_id}\n"
                f"🎮 <b>Никнейм:</b> <code>{steam_nick}</code>\n"
                f"🆔 <b>Steam ID:</b> <code>{steam_id}</code>\n"
                f"👤 <b>TG:</b> {tg_username}\n"
                f"🆔 <b>TG ID:</b> <code>{tg_id}</code>\n"
                f"🕒 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"<b>Проверьте и примите решение:</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"❌ Ошибка уведомления админа {admin_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Заявка отправлена!</b>\n\n"
        f"📋 ID заявки: <code>#{app_id}</code>\n\n"
        f"Модераторы проверят вашу заявку в ближайшее время.\n"
        f"Ожидайте уведомления в этом чате!\n\n"
        f"<i>Вы можете проверить статус командой /start</i>",
        reply_markup=main_menu(tg_id, has_pending_app=True),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "app_status")
async def app_status(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    apps = get_applications()
    user_app = next((app for app in apps if app[4] == str(user_id)), None)

    if not user_app:
        await callback.answer("❌ У вас нет заявок", show_alert=True)
        return

    status_emoji = {"ожидает": "🟡", "принят": "🟢", "отклонен": "🔴"}.get(user_app[6], "⚪")

    text = (
        f"📋 <b>Статус вашей заявки</b>\n\n"
        f"🆔 ID: <code>#{user_app[0]}</code>\n"
        f"🎮 Ник: <code>{user_app[1]}</code>\n"
        f"🕒 Дата: {user_app[5]}\n"
        f"{status_emoji} <b>Статус:</b> {user_app[6]}\n\n"
    )

    if user_app[6] == "принят":
        text += f"🎉 Поздравляем! Вот ссылка на группу:\n{GROUP_LINK}"
    elif user_app[6] == "отклонен":
        text += "❌ К сожалению, ваша заявка была отклонена."
    else:
        text += "⏳ Ваша заявка на рассмотрении. Ожидайте!"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# =========================
# 📬 АДМИН-ПАНЕЛЬ ЗАЯВОК
# =========================

@dp.callback_query_handler(lambda c: c.data == "applications_menu")
async def applications_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Только для админов", show_alert=True)
        return

    apps = get_applications(status="ожидает")
    keyboard = InlineKeyboardMarkup()

    if not apps:
        keyboard.add(InlineKeyboardButton("📭 Нет активных заявок", callback_data="none"))
    else:
        for app in apps:
            keyboard.add(InlineKeyboardButton(
                f"📬 #{app[0]} | {app[1]}",
                callback_data=f"app_view_{app[0]}"
            ))

    keyboard.add(
        InlineKeyboardButton("🟢 Принятые", callback_data="apps_accepted"),
        InlineKeyboardButton("🔴 Отклонённые", callback_data="apps_rejected")
    )
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(
        f"📬 <b>Заявки на вступление</b>\n\n"
        f"🟡 Ожидает: {len(apps)}\n\n"
        f"Выберите заявку для просмотра:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("app_"))
async def app_actions(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌", show_alert=True)
        return

    parts = callback.data.split("_")
    action = parts[1] if len(parts) > 1 else ""

    if action == "view":
        app_id = parts[2] if len(parts) > 2 else None
        if not app_id:
            await callback.answer("❌ Ошибка", show_alert=True)
            return

        app = get_application_by_id(app_id)
        if not app:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
        )
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="applications_menu"))

        text = (
            f"📬 <b>Заявка #{app['id']}</b>\n\n"
            f"🎮 <b>Никнейм:</b> <code>{app['nick']}</code>\n"
            f"🆔 <b>Steam ID:</b> <code>{app['steam_id']}</code>\n"
            f"👤 <b>TG:</b> {app['tg_username']}\n"
            f"🆔 <b>TG ID:</b> <code>{app['tg_id']}</code>\n"
            f"🕒 <b>Дата:</b> {app['date']}\n"
            f"🟡 <b>Статус:</b> {app['status']}\n\n"
            f"<b>Проверьте данные и примите решение:</b>"
        )

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if action == "accept":
        app_id = parts[2] if len(parts) > 2 else None
        if not app_id:
            await callback.answer("❌ Ошибка", show_alert=True)
            return

        app = get_application_by_id(app_id)
        if not app:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        update_application_status(app_id, "принят")

        member_added = add_new_member(app['nick'], app['steam_id'], app['tg_username'], app['tg_id'])

        if not member_added:
            await callback.answer("⚠️ Участник уже существует в таблице!", show_alert=True)
            return

        try:
            await bot.send_message(
                int(app['tg_id']),
                f"🎉 <b>Поздравляем! Ваша заявка принята!</b>\n\n"
                f"Добро пожаловать в клан <b>PET</b>!\n\n"
                f"🔗 <b>Ссылка на группу:</b>\n{GROUP_LINK}\n\n"
                f"Не забудьте представиться в теме «Общение»!",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"❌ Ошибка отправки ссылки: {e}")

        append_log("ЗАЯВКА_ПРИНЯТА", callback.from_user.full_name, callback.from_user.id, app['nick'])

        await callback.answer("✅ Заявка принята! Участник добавлен в таблицу", show_alert=True)
        await applications_menu(callback)
        return

    if action == "reject":
        app_id = parts[2] if len(parts) > 2 else None
        if not app_id:
            await callback.answer("❌ Ошибка", show_alert=True)
            return

        app = get_application_by_id(app_id)
        if not app:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        update_application_status(app_id, "отклонен")

        try:
            await bot.send_message(
                int(app['tg_id']),
                f"❌ <b>Заявка отклонена</b>\n\n"
                f"К сожалению, ваша заявка на вступление в клан PET была отклонена.\n\n"
                f"Вы можете подать новую заявку через 7 дней.",
                parse_mode="HTML"
            )
        except:
            pass

        append_log("ЗАЯВКА_ОТКЛОНЕНА", callback.from_user.full_name, callback.from_user.id, app['nick'])

        await callback.answer("❌ Заявка отклонена", show_alert=True)
        await applications_menu(callback)
        return

    if action in ["accepted", "rejected"]:
        status = "принят" if action == "accepted" else "отклонен"
        apps = get_applications(status=status)
        keyboard = InlineKeyboardMarkup()

        for app in apps[:10]:
            keyboard.add(InlineKeyboardButton(
                f"#{app[0]} | {app[1]}",
                callback_data=f"app_view_{app[0]}"
            ))

        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="applications_menu"))

        await callback.message.edit_text(
            f"{'🟢' if action == 'accepted' else '🔴'} <b>{'Принятые' if action == 'accepted' else 'Отклонённые'} заявки</b>\n\n"
            f"Всего: {len(apps)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    await callback.answer("❌ Неизвестное действие", show_alert=True)


# =========================
# 👤 ПРОФИЛЬ
# =========================

@dp.callback_query_handler(lambda c: c.data == "my_profile")
async def my_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    existing_nick = find_member_by_tg_id(user_id)

    if not existing_nick:
        await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
        return

    member_info = get_member_info(existing_nick)

    if not member_info:
        await callback.answer("❌ Данные не найдены", show_alert=True)
        return

    status_emoji = "✅" if member_info['desirable'] == "желателен" else "❌"

    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🎮 <b>Ник:</b> {member_info['nick']}\n"
        f"🎮 <b>Steam ID:</b> <code>{member_info['steam_id']}</code>\n"
        f"🎖 <b>Роль:</b> {member_info['role']}\n"
        f"⚠️ <b>Предупреждения:</b> {member_info['warns']}\n"
        f"👏 <b>Похвалы:</b> {member_info['praises']}\n"
        f"📊 <b>Рейтинг:</b> {member_info['score']}\n"
        f"📌 <b>Статус:</b> {status_emoji} {member_info['desirable']}\n"
        f"🆔 <b>TG ID:</b> <code>{user_id}</code>"
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# =========================
# 📋 КЛАН
# =========================

@dp.callback_query_handler(lambda c: c.data == "clan_list")
async def clan_list(callback: types.CallbackQuery):
    members = get_clan_members()
    keyboard = InlineKeyboardMarkup(row_width=2)
    for m in members:
        keyboard.insert(InlineKeyboardButton(m, callback_data=f"member_{m}"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text("📋 Выберите участника:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("member_"))
async def member_selected(callback: types.CallbackQuery, state: FSMContext):
    member = callback.data.replace("member_", "", 1)
    await state.update_data(member=member)
    is_admin = callback.from_user.id in ADMINS
    member_info = get_member_info(member) if is_admin else None
    keyboard = InlineKeyboardMarkup()

    if is_admin:
        keyboard.add(InlineKeyboardButton("⚠ Пред", callback_data="action_pred"))
        if member_info:
            status_emoji = "✅" if member_info['desirable'] == "желателен" else "❌"
            text = (
                f"👤 <b>Карточка: {member_info['nick']}</b>\n\n"
                f"🎮 <b>Steam:</b> <code>{member_info['steam_id']}</code>\n"
                f"🎖 <b>Роль:</b> {member_info['role']}\n"
                f"⚠️ <b>Предупреждения:</b> {member_info['warns']}\n"
                f"👏 <b>Похвалы:</b> {member_info['praises']}\n"
                f"📊 <b>Рейтинг:</b> {member_info['score']}\n"
                f"📌 <b>Статус:</b> {status_emoji} {member_info['desirable']}\n\n"
                f"<i>Выберите действие:</i>"
            )
        else:
            text = f"⚠️ <b>Участник {member}</b>\n\nИнформация не найдена.\n\n<i>Выберите действие:</i>"
    else:
        text = f"👤 <b>Участник:</b> {member}\n\n<i>Выберите действие:</i>"

    keyboard.add(InlineKeyboardButton("👏 Похвала", callback_data="action_praise"))
    keyboard.add(InlineKeyboardButton("⚖ Жалоба", callback_data="action_complaint"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data.startswith("action_"))
async def action_selected(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.replace("action_", "")
    await state.update_data(action=action)
    await ActionState.waiting_reason.set()
    msg = "📝 Опиши суть жалобы (или /cancel):" if action == "complaint" else "📝 Напиши причину (или /cancel):"
    await callback.message.answer(msg)


@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    member, action = data["member"], data["action"]
    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    user_id = user.id

    if action == "pred":
        if user_id not in ADMINS:
            await message.answer("❌ Нет прав", reply_markup=main_menu(user_id))
            await state.finish()
            return
        append_pred(member, message.text)
        append_log("ПРЕД", username, user_id, member)
        await message.answer("⚠ Пред записан ✅", reply_markup=main_menu(user_id))
    elif action == "praise":
        append_praise(member, username, message.text)
        append_log("ПОХВАЛА", username, user_id, member)
        await message.answer("👏 Похвала записана ✅", reply_markup=main_menu(user_id))
    elif action == "complaint":
        add_complaint(username, user_id, member, message.text)
        append_log("ЖАЛОБА", username, user_id, member)
        await message.answer("⚖ Жалоба отправлена ✅", reply_markup=main_menu(user_id))
    await state.finish()


# =========================
# 📸 ПРИЕМ ДОКАЗАТЕЛЬСТВ
# =========================

@dp.message_handler(state=ActionState.waiting_proof, content_types=types.ContentTypes.ANY)
async def process_proof(message: types.Message, state: FSMContext):
    data = await state.get_data()
    complaint_index = data.get("complaint_index")
    if complaint_index is None:
        await state.finish()
        return
    proof_info = ""
    if message.photo:
        proof_info = f"📷 Фото: {message.photo[-1].file_id}"
    elif message.document:
        proof_info = f"📄 Файл: {message.document.file_name}"
    elif message.video:
        proof_info = f"🎥 Видео: {message.video.file_id}"
    elif message.text:
        proof_info = f"📝 Текст: {message.text}"
    else:
        proof_info = "📎 Вложение"
    add_proof_to_complaint(complaint_index, proof_info)
    admin_id = data.get("admin_id")
    if admin_id:
        try:
            await bot.send_message(admin_id, f"📬 Доказательства по жалобе #{complaint_index}\n{proof_info}")
        except:
            pass
    await message.answer("✅ Доказательства приняты")
    await state.finish()


# =========================
# 🎖 РАЗРЯДЫ
# =========================

@dp.callback_query_handler(lambda c: c.data == "roles_menu")
async def roles_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(f"🪖 Сквадные ({count_by_role('сквадной')})", callback_data="role_сквадной"))
    keyboard.add(InlineKeyboardButton(f"🎯 Пехи ({count_by_role('пех')})", callback_data="role_пех"))
    keyboard.add(InlineKeyboardButton(f"🔧 Техи ({count_by_role('тех')})", callback_data="role_тех"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text("Выбери категорию:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("role_"))
async def show_role_members(callback: types.CallbackQuery):
    role = callback.data.replace("role_", "")
    members = get_members_by_role(role)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for m in members:
        keyboard.insert(InlineKeyboardButton(m, callback_data=f"editrole_{m}"))
    keyboard.add(InlineKeyboardButton("⬅ Назад", callback_data="roles_menu"))
    await callback.message.edit_text(f"{role.upper()} ({len(members)}):", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("editrole_"))
async def edit_role(callback: types.CallbackQuery, state: FSMContext):
    member = callback.data.replace("editrole_", "")
    await state.update_data(role_member=member)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🪖 Сквадной", callback_data="setrole_сквадной"),
        InlineKeyboardButton("🎯 Пех", callback_data="setrole_пех"),
        InlineKeyboardButton("🔧 Тех", callback_data="setrole_тех")
    )
    keyboard.add(InlineKeyboardButton("⬅ Назад", callback_data="roles_menu"))
    await callback.message.edit_text(f"Переназначить роль для {member}:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("setrole_"))
async def set_new_role(callback: types.CallbackQuery, state: FSMContext):
    new_role = callback.data.replace("setrole_", "")
    member = (await state.get_data()).get("role_member")
    if member:
        update_role(member, new_role)
        await callback.message.edit_text(f"✅ Роль для {member} обновлена на {new_role}",
                                         reply_markup=main_menu(callback.from_user.id))
    else:
        await callback.message.edit_text("❌ Ошибка: участник не найден")


# =========================
# 📊 СТАТИСТИКА
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("📅 За неделю", callback_data="stats_week"),
        InlineKeyboardButton("📈 За всё время", callback_data="stats_all")
    )
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text("📊 Выберите период для статистики:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == "stats_week")
async def stats_week(callback: types.CallbackQuery):
    top = get_top_praises(weeks=1)
    text = "📭 За неделю похвал ещё нет." if not top else (
            "🏆 <b>ТОП-10 за неделю:</b>\n\n" +
            "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="stats"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "stats_all")
async def stats_all(callback: types.CallbackQuery):
    top = get_top_praises(weeks=None)
    text = "📭 Похвал ещё нет." if not top else (
            "🏆 <b>ТОП-10 за всё время:</b>\n\n" +
            "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="stats"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# =========================
# 📄 ШАБЛОНЫ ОТЧЁТОВ (С ЛОГИРОВАНИЕМ)
# =========================

@dp.callback_query_handler(lambda c: c.data == "templates_menu")
async def templates_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Только для админов", show_alert=True)
        return

    templates = get_report_templates()
    keyboard = InlineKeyboardMarkup()

    for t in templates:
        status = "✅" if t["active"] else "⭕"
        keyboard.add(InlineKeyboardButton(
            f"{status} {t['name']}",
            callback_data=f"tmpl_view_{t['id']}"
        ))

    keyboard.add(
        InlineKeyboardButton("➕ Добавить шаблон", callback_data="tmpl_add"),
        InlineKeyboardButton("🔄 Протестировать отчёт", callback_data="tmpl_test"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
    )

    await callback.message.edit_text(
        "📄 <b>Шаблоны еженедельных отчётов</b>\n\n"
        "Нажмите на шаблон для редактирования.\n"
        "Зелёная галочка = активный шаблон.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query_handler(lambda c: c.data.startswith("tmpl_"))
async def template_actions(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌", show_alert=True)
        return

    parts = callback.data.split("_")
    action = parts[1] if len(parts) > 1 else ""
    admin = callback.from_user
    admin_name = f"@{admin.username}" if admin.username else admin.full_name
    admin_id = admin.id

    if action == "test":
        report = generate_weekly_report()
        await callback.message.answer(
            f"🧪 <b>Тест отчёта:</b>\n\n{report}",
            parse_mode="HTML"
        )
        await callback.answer("✅ Отчёт сгенерирован", show_alert=True)
        return

    if action == "add":
        await state.update_data(template_action="add")
        await ActionState.new_template_name.set()
        await callback.message.answer("📝 Введите название нового шаблона:")
        return

    if action == "view":
        template_id = parts[2] if len(parts) > 2 else None
        if not template_id:
            await callback.answer("❌ Ошибка: не указан ID шаблона", show_alert=True)
            return

        templates = get_report_templates()
        template = next((t for t in templates if t["id"] == template_id), None)

        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✏️ Изменить текст", callback_data=f"tmpl_edit_text_{template_id}"),
            InlineKeyboardButton("🔄 Сделать активным" if not template["active"] else "✅ Уже активен",
                                 callback_data=f"tmpl_activate_{template_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"tmpl_delete_{template_id}")
        )
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="templates_menu"))

        preview = template["text"][:200] + "..." if len(template["text"]) > 200 else template["text"]

        await callback.message.edit_text(
            f"📄 <b>Шаблон: {template['name']}</b>\n\n"
            f"📋 <i>Предпросмотр:</i>\n<code>{preview}</code>\n\n"
            f"🔁 Статус: {'✅ Активен' if template['active'] else '⭕ Не активен'}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    if action == "edit" and len(parts) >= 4 and parts[2] == "text":
        template_id = parts[3] if len(parts) > 3 else None
        if not template_id:
            await callback.answer("❌ Ошибка: не указан ID шаблона", show_alert=True)
            return

        await state.update_data(template_action="edit", template_id=template_id)
        await ActionState.editing_template.set()

        templates = get_report_templates()
        template = next((t for t in templates if t["id"] == template_id), None)
        current_text = template["text"] if template else "Шаблон не найден"

        await callback.message.answer(
            f"✏️ Введите новый текст шаблона.\n\n"
            f"📋 <i>Текущий текст:</i>\n<code>{current_text[:300]}</code>\n\n"
            f"Доступные переменные:\n"
            f"<code>{{top_list}}</code> — список лидеров\n"
            f"<code>{{date}}</code> — текущая дата\n"
            f"<code>{{week_start}}</code> — дата начала недели\n\n"
            f"Пример:\n"
            f"<code>🏆 Итоги за {{week_start}}–{{date}}!\n\n{{top_list}}\n\nТак держать! 💪</code>",
            parse_mode="HTML"
        )
        return

    if action == "activate":
        template_id = parts[2] if len(parts) > 2 else None
        if not template_id:
            await callback.answer("❌ Ошибка: не указан ID шаблона", show_alert=True)
            return

        templates = get_report_templates()
        for t in templates:
            update_template(t["id"], "active", "нет")

        update_template(template_id, "active", "да")
        append_log("АКТИВАЦИЯ_ШАБЛОНА", admin_name, admin_id, f"Шаблон ID:{template_id}")

        await callback.answer("✅ Шаблон активирован!", show_alert=True)
        await templates_menu_show(callback.message)
        return

    if action == "delete":
        template_id = parts[2] if len(parts) > 2 else None
        if not template_id:
            await callback.answer("❌ Ошибка: не указан ID шаблона", show_alert=True)
            return

        ws = get_templates_sheet()
        rows = ws.get_all_values()

        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == template_id:
                ws.delete_rows(idx, idx)
                break

        append_log("УДАЛЕНИЕ_ШАБЛОНА", admin_name, admin_id, f"Шаблон ID:{template_id}")

        await callback.answer("🗑 Шаблон удалён", show_alert=True)
        await templates_menu_show(callback.message)
        return

    await callback.answer("❌ Неизвестное действие", show_alert=True)


async def templates_menu_show(message: types.Message):
    templates = get_report_templates()
    keyboard = InlineKeyboardMarkup()

    for t in templates:
        status = "✅" if t["active"] else "⭕"
        keyboard.add(InlineKeyboardButton(
            f"{status} {t['name']}",
            callback_data=f"tmpl_view_{t['id']}"
        ))

    keyboard.add(
        InlineKeyboardButton("➕ Добавить шаблон", callback_data="tmpl_add"),
        InlineKeyboardButton("🔄 Протестировать отчёт", callback_data="tmpl_test"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
    )

    await message.edit_text(
        "📄 <b>Шаблоны еженедельных отчётов</b>\n\n"
        "Нажмите на шаблон для редактирования.\n"
        "Зелёная галочка = активный шаблон.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query_handler(lambda c: c.data.startswith("tmpl_edit_text_"))
async def edit_template_text(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌", show_alert=True)
        return

    template_id = callback.data.replace("tmpl_edit_text_", "")
    await state.update_data(template_action="edit", template_id=template_id)
    await ActionState.editing_template.set()

    await callback.message.answer(
        "✏️ Введите новый текст шаблона.\n\n"
        "Доступные переменные:\n"
        "<code>{top_list}</code> — список лидеров\n"
        "<code>{date}</code> — текущая дата\n"
        "<code>{week_start}</code> — дата начала недели\n\n"
        "Пример:\n"
        "<code>🏆 Итоги за {week_start}–{date}!\n\n{top_list}\n\nТак держать! 💪</code>",
        parse_mode="HTML"
    )


@dp.message_handler(state=ActionState.editing_template)
async def save_template_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_id = data.get("template_id")

    if not template_id:
        await message.answer("❌ Ошибка: не указан шаблон")
        await state.finish()
        return

    new_text = message.text
    update_template(template_id, "text", new_text)

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    append_log("ИЗМЕНЕНИЕ_ШАБЛОНА", username, user.id, f"Шаблон ID:{template_id}")

    await message.answer("✅ Текст шаблона обновлен!", reply_markup=main_menu(message.from_user.id))
    await state.finish()


@dp.message_handler(state=ActionState.new_template_name)
async def save_template_name(message: types.Message, state: FSMContext):
    await state.update_data(new_template_name=message.text)
    await ActionState.new_template_text.set()
    await message.answer("📝 Теперь введите текст шаблона (используйте {top_list}, {date}, {week_start}):")


@dp.message_handler(state=ActionState.new_template_text)
async def save_new_template(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("new_template_name")
    text = message.text

    if not name or not text:
        await message.answer("❌ Ошибка сохранения")
        await state.finish()
        return

    new_id = add_template(name, text)

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    append_log("СОЗДАНИЕ_ШАБЛОНА", username, user.id, f"Шаблон '{name}' ID:{new_id}")

    await message.answer(f"✅ Шаблон '{name}' создан! ID: {new_id}", reply_markup=main_menu(message.from_user.id))
    await state.finish()


# =========================
# 📝 ЛОГИ
# =========================

@dp.callback_query_handler(lambda c: c.data == "logs")
async def logs(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Доступ только для админов", show_alert=True)
        return

    logs_data = get_logs()[-10:]

    if len(logs_data) <= 1:
        text = "📭 Логи пусты"
    else:
        text = "🕒 Последние 10 действий:\n\n"
        for row in logs_data[-1:0:-1]:
            if len(row) >= 5:
                action = row[0].replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
                username = row[1].replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
                target = row[3].replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
                date = row[4].replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
                text += f"`{date}` | {action} | {username} → {target}\n"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query_handler(lambda c: c.data == "clear_logs")
async def clear_logs_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌", show_alert=True)
        return
    clear_logs()
    await callback.message.edit_text("✅ Логи очищены", reply_markup=main_menu(callback.from_user.id))


# =========================
# ⚖ ЖАЛОБЫ
# =========================

@dp.callback_query_handler(lambda c: c.data == "complaints")
async def complaints_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Только для админов", show_alert=True)
        return
    rows = get_complaints()
    keyboard = InlineKeyboardMarkup()
    active_found = False
    for i, row in enumerate(rows[1:]):
        if len(row) < 6:
            continue
        if row[5] != "активна":
            continue
        active_found = True
        target = row[2] if len(row) > 2 else "Неизвестно"
        keyboard.add(InlineKeyboardButton(f"🔴 {target}", callback_data=f"complaint_{i}"))
    if not active_found:
        keyboard.add(InlineKeyboardButton("📭 Нет активных жалоб", callback_data="none"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text("⚖ Активные жалобы:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("complaint_"))
async def complaint_actions(callback: types.CallbackQuery):
    data = callback.data.split("_")
    admin_name = callback.from_user.full_name
    admin_username = f"@{callback.from_user.username}" if callback.from_user.username else ""
    admin_info = f"{admin_name} {admin_username}".strip()

    if data[1] == "pred" and len(data) >= 3:
        try:
            index = int(data[2])
        except:
            return await callback.answer("❌ Ошибка индекса", show_alert=True)
        rows = get_complaints()
        if index + 1 >= len(rows):
            return await callback.answer("❌ Не найдено", show_alert=True)
        row = rows[index + 1]
        violator = row[2] if len(row) > 2 else "Неизвестно"
        reason = row[3] if len(row) > 3 else "Без указания"
        sender_id = row[1] if len(row) > 1 else None

        append_pred(violator, f"По жалобе: {reason}")
        append_log(f"ПРЕД_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, violator)
        close_complaint(index, closed_by=admin_info)

        if sender_id:
            try:
                await bot.send_message(int(sender_id), f"✅ Жалоба на {violator} рассмотрена. Выдан ПРЕД.",
                                       parse_mode="HTML")
            except:
                pass
        await callback.message.edit_text(f"⚠ ПРЕД выдан {violator}. Жалоба закрыта ✅",
                                         reply_markup=main_menu(callback.from_user.id))
        return

    if data[1] == "request" and data[2] == "proof" and len(data) >= 4:
        try:
            index = int(data[3])
        except:
            return await callback.answer("❌ Ошибка", show_alert=True)
        rows = get_complaints()
        if index + 1 >= len(rows):
            return await callback.answer("❌ Не найдено", show_alert=True)
        row = rows[index + 1]
        sender_id = row[1] if len(row) > 1 else None
        target = row[2] if len(row) > 2 else "неизвестно"

        append_log(f"ЗАПРОС_ДОКОВ_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id,
                   target)

        if sender_id:
            try:
                await dp.storage.set_state(chat=int(sender_id), user=int(sender_id), state=ActionState.waiting_proof)
                await dp.storage.set_data(chat=int(sender_id), user=int(sender_id),
                                          data={"complaint_index": index, "admin_id": callback.from_user.id})
                await bot.send_message(int(sender_id),
                                       f"🔍 Запрошены доказательства по жалобе на {target}.\nОтправьте скриншоты или /cancel",
                                       parse_mode="HTML")
                await callback.answer("📩 Запрос отправлен", show_alert=True)
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
        else:
            await callback.answer("❌ Не найден ID", show_alert=True)
        return

    if data[1] == "close" and data[2] == "noaction" and len(data) >= 4:
        try:
            index = int(data[3])
        except:
            return await callback.answer("❌ Ошибка", show_alert=True)
        rows = get_complaints()
        if index + 1 >= len(rows):
            return await callback.answer("❌ Не найдено", show_alert=True)
        row = rows[index + 1]
        sender_id = row[1] if len(row) > 1 else None
        target = row[2] if len(row) > 2 else "неизвестно"

        append_log(f"ЖАЛОБА_ЗАКРЫТА_БЕЗ_ДЕЙСТВИЙ [{admin_info}]", callback.from_user.full_name, callback.from_user.id,
                   target)
        close_complaint(index, closed_by=admin_info)

        if sender_id:
            try:
                await bot.send_message(int(sender_id), f"ℹ️ Жалоба на {target} закрыта без санкций.", parse_mode="HTML")
            except:
                pass
        await callback.message.edit_text(f"✅ Жалоба закрыта", reply_markup=main_menu(callback.from_user.id))
        return

    try:
        index = int(data[1])
    except:
        return await callback.answer("❌", show_alert=True)
    rows = get_complaints()
    if index + 1 >= len(rows):
        return await callback.answer("❌ Не найдено", show_alert=True)
    row = rows[index + 1]
    from_user = row[0] if len(row) > 0 else "?"
    to_member = row[2] if len(row) > 2 else "?"
    reason = row[3] if len(row) > 3 else "Нет описания"
    date = row[4] if len(row) > 4 else ""
    status = row[5] if len(row) > 5 else "активна"
    proof = row[6] if len(row) > 6 else "Нет"
    closed_by = row[7] if len(row) > 7 else ""

    text = (
        f"⚖ <b>ЖАЛОБА #{index}</b>\n\n"
        f"👤 <b>От:</b> {from_user}\n🎯 <b>На:</b> {to_member}\n"
        f"📝 <b>Причина:</b> {reason}\n🕒 <b>Дата:</b> {date}\n"
        f"📎 <b>Доки:</b> {proof if proof else 'Нет'}\n🔖 <b>Статус:</b> {status}"
    )
    if closed_by:
        text += f"\n🔒 <b>Закрыл:</b> {closed_by}"

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("⚠ ПРЕД + закрыть", callback_data=f"complaint_pred_{index}"))
    keyboard.add(InlineKeyboardButton("📸 Запросить доки", callback_data=f"complaint_request_proof_{index}"))
    keyboard.add(InlineKeyboardButton("❌ Закрыть (ничего)", callback_data=f"complaint_close_noaction_{index}"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# =========================
# 🛠 ВРЕМЕННЫЕ КОМАНДЫ (можно удалить после настройки)
# =========================

@dp.message_handler(commands=["test_report"])
async def test_report_cmd(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    report = generate_weekly_report()
    if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
        await bot.send_message(
            chat_id=REPORT_CHAT_ID,
            text=report,
            parse_mode="HTML",
            message_thread_id=int(REPORT_TOPIC_ID)
        )
    else:
        await bot.send_message(
            chat_id=REPORT_CHAT_ID,
            text=report,
            parse_mode="HTML"
        )
    await message.answer("✅ Отчёт отправлен в группу!")


@dp.message_handler(commands=["getid"])
async def get_chat_id(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    chat_id = message.chat.id
    thread_id = message.message_thread_id if hasattr(message, 'message_thread_id') else None
    text = f"🆔 <b>ID чата:</b> <code>{chat_id}</code>"
    if thread_id:
        text += f"\n📑 <b>ID темы:</b> <code>{thread_id}</code>"
    await message.answer(text, parse_mode="HTML")


# =========================
# ⏰ ПЛАНИРОВЩИК
# =========================

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))


async def scheduled_report_job():
    logging.info("⏰ Запуск задачи: отправка отчёта")
    await send_weekly_report()


async def on_startup(_):
    if REPORT_CHAT_ID:
        scheduler.add_job(
            scheduled_report_job,
            trigger=CronTrigger(hour=18, minute=30, day_of_week="sat", timezone=pytz.timezone("Europe/Moscow")),
            id="weekly_report",
            replace_existing=True
        )
        scheduler.start()
        logging.info("⏰ Планировщик запущен: отчёт каждую субботу в 18:30 МСК")
    else:
        logging.warning("⚠️ REPORT_CHAT_ID не задан — авто-отчёты отключены")


async def on_shutdown(_):
    scheduler.shutdown()


# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)