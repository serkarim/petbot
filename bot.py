import logging
from datetime import datetime, timedelta
import os
import json
import re
import html as html_lib
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from gdrive import upload_video_to_drive
import pytz
import time
from datetime import datetime
from krestgg_parser import parser as krest_parser  # импорт нашего парсера
from aiogram.types import WebAppInfo  # ← Добавить в импорты
import asyncio
# =========================
# 🔧 НАСТРОЙКА LOGGER
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# =========================
# 🔐 ENV
# =========================
TOKEN = os.getenv("TOKEN")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID")
REPORT_TOPIC_ID = os.getenv("REPORT_TOPIC_ID")
WARN_CHAT_ID = os.getenv("WARN_CHAT_ID")
GROUP_LINK = os.getenv("GROUP_LINK")

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
def get_member_preds_history(nickname):
    """Получить историю предупреждений участника"""
    try:
        ws = sheet.worksheet("преды")
        rows = ws.get_all_values()[1:]  # Пропускаем заголовок
        preds = []
        for row in rows:
            if len(row) >= 3 and row[0].strip() == nickname.strip():
                preds.append(row)
        return preds[-10:]  # Последние 10
    except Exception as e:
        logging.error(f"❌ get_member_preds_history: {e}")
        return []

def get_member_praises_history(nickname):
    """Получить историю похвал участника"""
    try:
        ws = sheet.worksheet("Похвала")
        rows = ws.get_all_values()[1:]  # Пропускаем заголовок
        praises = []
        for row in rows:
            if len(row) >= 4 and row[0].strip() == nickname.strip():
                praises.append(row)
        return praises[-10:]  # Последние 10
    except Exception as e:
        logging.error(f"❌ get_member_praises_history: {e}")
        return []
def get_member_preds(nickname):
    try:
        ws = sheet.worksheet("преды")
        rows = ws.get_all_values()[1:]  # Пропускаем заголовок
        preds = []
        for row in rows:
            if len(row) >= 3 and row[0].strip() == nickname.strip():
                preds.append(row)
        return preds[-10:]  # Возвращаем последние 10
    except Exception as e:
        logging.error(f"❌ get_member_preds: {e}")
        return []

def get_member_praises(nickname):
    try:
        ws = sheet.worksheet("Похвала")
        rows = ws.get_all_values()[1:]  # Пропускаем заголовок
        praises = []
        for row in rows:
            if len(row) >= 4 and row[0].strip() == nickname.strip():
                praises.append(row)
        return praises[-10:]  # Возвращаем последние 10
    except Exception as e:
        logging.error(f"❌ get_member_praises: {e}")
        return []
def get_clan_members():
    ws = sheet.worksheet("участники клана")
    return [v for v in ws.col_values(1) if v.strip()]

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
def get_clips_sheet():
    """Получает или создаёт лист 'клипы' в Google Sheets"""
    try:
        return sheet.worksheet("клипы")
    except:
        # Если листа нет — создаём
        ws = sheet.add_worksheet("клипы", rows=100, cols=10)
        ws.append_row([
            "ID", "Ник клана", "TG Username", "TG ID",
            "Drive Link", "Drive File ID", "Описание",
            "Дата", "Статус", "Дата одобрения", "Одобрил"
        ])
        return ws
def find_member_by_tg_id(tg_id):
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 9 and row[8].strip() == str(tg_id):
            return row[0]
    return None

def update_member_tg_data(nickname, tg_username, tg_id):
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for idx, row in enumerate(rows[1:], start=2):
        if row[0].strip() == nickname.strip():
            ws.update_cell(idx, 8, tg_username)
            ws.update_cell(idx, 9, str(tg_id))
            return True
    return False

def add_new_member(nickname, steam_id, tg_username, tg_id):
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 2 and row[1].strip() == steam_id.strip():
            return False
        if len(row) >= 9 and row[8].strip() == str(tg_id).strip():
            return False
    ws.append_row([nickname, steam_id, "новичок", "0", "0", "0", "желателен", tg_username, str(tg_id)])
    return True

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
    date = get_msk_time().strftime("%d.%m.%Y %H:%M")
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
                'id': row[0], 'nick': row[1], 'steam_id': row[2],
                'tg_username': row[3], 'tg_id': row[4], 'date': row[5],
                'status': row[6] if len(row) > 6 else 'ожидает'
            }
    return None

def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = get_msk_time().strftime("%d.%m.%Y")
    ws.append_row([member, reason, date])

def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    date = get_msk_time().strftime("%d.%m.%Y")
    ws.append_row([member, from_user, reason, date])

def append_log(action, username, user_id, to_member):
    ws = sheet.worksheet("логи")
    date = get_msk_time().strftime("%d.%m.%Y %H:%M")
    ws.append_row([action, username, user_id, to_member, date])

def get_logs():
    return sheet.worksheet("логи").get_all_values()


# =========================
# 🔇 ЛОГИРОВАНИЕ МУТОВ
# =========================
def append_mute_log(violator_nick: str, violator_id: int, moderator_nick: str, moderator_id: int, reason: str,
                    duration: str):
    """Добавляет запись о муте в лист 'муты'"""
    try:
        # Пытаемся получить лист, если нет — создаём
        try:
            ws = sheet.worksheet("муты")
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet("муты", rows=100, cols=8)
            ws.append_row(
                ["Дата", "Нарушитель", "ID нарушителя", "Модератор", "ID модератора", "Причина", "Длительность",
                 "Статус"])

        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row(
            [date, violator_nick, str(violator_id), moderator_nick, str(moderator_id), reason, duration, "активен"])
        return True
    except Exception as e:
        logging.error(f"❌ append_mute_log: {e}")
        return False


def is_moderator(user_id: int) -> bool:
    """Проверяет, является ли пользователь модератором/админом"""
    # Проверяем по списку ADMINS из .env
    if user_id in ADMINS:
        return True
    # Проверяем по таблице "участники клана" (роль модератор)
    try:
        ws = sheet.worksheet("участники клана")
        rows = ws.get_all_values()
        for row in rows[1:]:
            if len(row) >= 9 and row[8].strip() == str(user_id):
                role = row[2].lower() if len(row) > 2 else ""
                return role in ["модератор", "админ", "главный", "tech_admin"]
    except Exception as e:
        logging.error(f"❌ is_moderator check: {e}")
    return False
# ---------- ВРЕМЯ (MSK) ----------
def get_msk_time():
    """Получает текущее время по Москве"""
    return datetime.now(pytz.timezone("Europe/Moscow"))
def clear_logs():
    ws = sheet.worksheet("логи")
    ws.clear()
    ws.append_row(["Тип", "Username", "UserID", "Кому", "Дата"])

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
                date_str = row[3].strip() if len(row) > 3 else None
                if not date_str:
                    continue
                date = datetime.strptime(date_str, "%d.%m.%Y")
                if date < datetime.now() - timedelta(weeks=weeks):
                    continue
            counter[member] = counter.get(member, 0) + 1
        except:
            continue
    return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:10]

def get_templates_sheet():
    try:
        return sheet.worksheet("Шаблоны отчётов")
    except:
        ws = sheet.add_worksheet("Шаблоны отчётов", rows=100, cols=4)
        ws.append_row(["ID", "Название", "Текст шаблона", "Активен"])
        ws.append_row(["1", "Стандарт", "🏆 Итоги недели!\n{top_list}\nТак держать! 💪", "да"])
        return ws

def get_report_templates():
    ws = get_templates_sheet()
    rows = ws.get_all_values()[1:]
    return [{"id": r[0], "name": r[1], "text": r[2], "active": r[3].lower() == "да"} for r in rows if len(r) >= 4 and r[0].strip()]

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

def generate_weekly_report():
    top = get_top_praises(weeks=1)
    template = get_active_template()
    if not template:
        return "❌ Не найден активный шаблон отчёта"
    top_text = "📭 На этой неделе похвал ещё нет. Давайте активнее! 🔥" if not top else "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
    msk_time = get_msk_time()
    return template["text"].format(top_list=top_text, date=msk_time.now().strftime("%d.%m.%Y"), week_start=(msk_time - timedelta(days=7)).strftime("%d.%m.%Y"))

async def send_weekly_report():
    if not REPORT_CHAT_ID:
        logging.warning("REPORT_CHAT_ID не задан")
        return
    report_text = generate_weekly_report()
    try:
        if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
            await bot.send_message(chat_id=REPORT_CHAT_ID, text=report_text, parse_mode="HTML", message_thread_id=int(REPORT_TOPIC_ID))
        else:
            await bot.send_message(chat_id=REPORT_CHAT_ID, text=report_text, parse_mode="HTML")
        logging.info("✅ Еженедельный отчёт отправлен")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки отчёта: {e}")

def add_complaint(from_user, from_user_id, to_member, reason):
    ws = sheet.worksheet("жалобы")
    date = get_msk_time().strftime("%d.%m.%Y %H:%M")
    ws.append_row([from_user, str(from_user_id), to_member, reason, date, "активна", "", ""])

def get_complaints():
    return sheet.worksheet("жалобы").get_all_values()

def update_complaint_field(index, column, value):
    sheet.worksheet("жалобы").update_cell(index + 2, column, value)

def close_complaint(index, closed_by=None):
    update_complaint_field(index, 6, "закрыта")
    if closed_by:
        try:
            ws = sheet.worksheet("жалобы")
            timestamp = get_msk_time().strftime("%d.%m.%Y %H:%M")
            ws.update_cell(index + 2, 8, f"{closed_by} | {timestamp}")
        except:
            pass
def add_proof_to_complaint(index, proof_text):
    ws = sheet.worksheet("жалобы")
    current = ws.cell(index + 2, 7).value or ""
    ws.update_cell(index + 2, 7, f"{current}\n{proof_text}" if current else proof_text)

# =========================
# 🤖 INIT
# =========================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# =========================
# MENU
# =========================


# Добавь переменную (после TOKEN, ADMINS)
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-app.railway.app")

def main_menu(user_id, is_registered=False, has_pending_app=False):
    keyboard = InlineKeyboardMarkup()
    if is_registered:
        keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
        keyboard.add(InlineKeyboardButton("📊 Статистика", callback_data="stats"))
        keyboard.add(InlineKeyboardButton("⚖ Жалобы", callback_data="complaints"))
        keyboard.add(InlineKeyboardButton("👤 Мой профиль", callback_data="my_profile"))
        keyboard.add(InlineKeyboardButton("🎬 Отправить клип", callback_data="submit_clip"))
        keyboard.add(InlineKeyboardButton( "🎫 Написать администрации ", callback_data= "ticket_create"))
        # 🆕 КНОПКА MINI APP
        keyboard.add(InlineKeyboardButton(
            "📱 Mini App",
            web_app=WebAppInfo(url=MINI_APP_URL)
        ))
    else:
        keyboard.add(InlineKeyboardButton("📝 Подать заявку", callback_data="apply_start"))
    if has_pending_app:
        keyboard.add(InlineKeyboardButton("📋 Статус заявки", callback_data="app_status"))
    if user_id in ADMINS:
        keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
        keyboard.add(InlineKeyboardButton("📢 Оповещения", callback_data="notify_menu"))
        keyboard.add(InlineKeyboardButton("📝 Логи", callback_data="logs"))
        keyboard.add(InlineKeyboardButton("📄 Шаблоны отчётов", callback_data="templates_menu"))
        keyboard.add(InlineKeyboardButton("📬 Заявки", callback_data="applications_menu"))
    return keyboard

# Добавь команду /app


# =========================
# FSM
# =========================
class ActionState(StatesGroup):
    waiting_reason = State()
    waiting_proof = State()
    editing_template = State()
    new_template_name = State()
    new_template_text = State()
    reg_type_choice = State()
    reg_rules = State()
    reg_steam_nick = State()
    reg_steam_id = State()
    reg_confirm = State()
    reg_select_existing = State()
    reg_existing_confirm = State()
    clip_waiting_video = State()
    clip_waiting_desc = State()
    clip_waiting_video = State()        # Ожидание видео файла
    clip_waiting_desc = State()         # Ожидание описания для файла
    clip_link_waiting_url = State()     # 🔥 Ожидание ссылки
    clip_link_waiting_desc = State()    # 🔥 Ожидание описания для ссылки
    waiting_user_msg = State()
    waiting_court_time = State()      # 🆕 Время суда
    waiting_court_reason = State()    # 🆕 Причина вызова
class TicketState(StatesGroup):
    waiting_user_msg = State()
# =========================
# START / CANCEL / BACK
# =========================
@dp.message_handler(commands=["start"])
async def start(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        existing_nick = find_member_by_tg_id(user_id)

        # 🎨 ФОТО ДЛЯ [PET] КИРЮХА (замени ID на его Telegram ID)
        KIRYUKHA_ID = 123456  # ID из твоих логов (@stone_lord)
        PHOTO_URL = "https://github.com/serkarim/petbot/blob/4f8525d03638a5df38e357a3fc34402889592a60/photo_2026-03-08_11-27-57.jpg"  # Ссылка на фото

        if existing_nick:
            safe_nick = html_lib.escape(existing_nick)

            # Если это КИРЮХА — отправляем с фото
            if user_id == KIRYUKHA_ID:
                try:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=PHOTO_URL,  # Или file_id: "AgACAgIA..."
                        caption=(
                            f"👋 <b>С возвращением, Шеф!</b>\n\n"
                            f"✅ Вы зарегистрированы как <b>{safe_nick}</b>\n\n"
                            f"🎮 Клан PET | Бот v2.0"
                        ),
                        reply_markup=main_menu(user_id, is_registered=True),
                        parse_mode="HTML"
                    )
                    return
                except Exception as e:
                    logging.error(f"❌ Ошибка отправки фото: {e}")
                    # Если фото не отправилось — отправляем обычное сообщение

            # Обычное приветствие для остальных
            await message.answer(
                f"👋 <b>С возвращением, {username}!</b>\n\n"
                f"✅ Вы уже зарегистрированы как <b>{safe_nick}</b>",
                reply_markup=main_menu(user_id, is_registered=True),
                parse_mode="HTML"
            )
        else:
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)
            await state.update_data(tg_username=username, tg_id=user_id)
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("📝 Подать заявку", callback_data="apply_start"))
            if has_pending:
                keyboard.add(InlineKeyboardButton("📋 Статус заявки", callback_data="app_status"))
            await message.answer(
                f"👋 <b>Привет, {username}!</b>\n\n"
                f"Чтобы вступить в клан:\n"
                f"1️⃣ Подать заявку\n"
                f"2️⃣ Дождаться проверки\n"
                f"3️⃣ Получить ссылку\n\n"
                f"<b>Готовы?</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except Exception as e:
        logging.error(f"❌ start: {e}")
@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending))
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ back_menu: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.message_handler(state='*', commands=['cancel'])
async def cancel_handler(message: types.Message, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state is None:
            return

        user_id = message.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)

        await state.finish()

        await message.answer(
            "✅ Действие отменено",
            reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending)
        )
    except Exception as e:
        logging.error(f"❌ cancel: {e}")


@dp.message_handler(commands=["app"])
async def open_app(message: types.Message):
    await message.answer(
        "📱 Открываю Mini App...",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🚀 Открыть приложение",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        )
    )
@dp.callback_query_handler(lambda c: c.data == "submit_clip")
async def start_clip_submission(callback: types.CallbackQuery, state: FSMContext):
    """Выбор способа отправки клипа"""
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)

        if not existing_nick:
            await callback.answer("❌ Только для зарегистрированных участников", show_alert=True)
            return

        await state.update_data(
            clip_user_nick=existing_nick,
            clip_user_id=user_id,
            clip_username=callback.from_user.username or callback.from_user.full_name
        )

        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("📤 Загрузить файл (до 20 МБ)", callback_data="clip_method_file"),
            InlineKeyboardButton("🔗 Отправить ссылку (любой размер)", callback_data="clip_method_link"),
            InlineKeyboardButton("❌ Отмена", callback_data="clip_cancel")
        )

        await callback.message.edit_text(
            "🎬 **Отправка клипа**\n\n"
            "Выберите способ отправки:\n\n"
            "📤 **Загрузить файл**\n"
            "• Макс. размер: 20 МБ\n"
            "• Бот загрузит на Google Drive\n"
            "• Быстро и удобно\n\n"
            "🔗 **Отправить ссылку**\n"
            "• Без лимита размера\n"
            "• Загрузите в своё облако (Google Drive, Яндекс.Диск и т.д.)\n"
            "• Отправьте ссылку боту\n\n"
            "⚠️ Если видео больше 20 МБ — выбирайте ссылку!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ start_clip_submission: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
@dp.callback_query_handler(lambda c: c.data == "clip_cancel", state="*")
async def cancel_clip_submission(callback: types.CallbackQuery, state: FSMContext):
    """Отмена отправки клипа"""
    try:
        await state.finish()
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        await callback.message.edit_text(
            "✅ Отмена. Клип не отправлен.",
            reply_markup=main_menu(user_id, is_registered=(existing_nick is not None))
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ cancel_clip_submission: {e}")


# =========================
# 📤 МЕТОД: ЗАГРУЗКА ФАЙЛА
# =========================

@dp.callback_query_handler(lambda c: c.data == "clip_method_file")
async def clip_method_file(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал загрузку файла"""
    try:
        await ActionState.clip_waiting_video.set()

        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("❌ Отмена", callback_data="clip_cancel")
        )

        await callback.message.edit_text(
            "📤 **Загрузка файла**\n\n"
            "📹 Отправьте видеофайл:\n"
            "• Макс. размер: **20 МБ**\n"
            "• Формат: MP4, MOV\n"
            "• Длительность: до 1 минуты рекомендуется\n\n"
            "🔙 Нажмите «Отмена» в любой момент",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ clip_method_file: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.message_handler(state=ActionState.clip_waiting_video, content_types=types.ContentTypes.VIDEO)
async def receive_clip_video(message: types.Message, state: FSMContext):
    """Получение видео файла"""
    try:
        video = message.video
        video_file_id = video.file_id
        file_size = video.file_size  # ← БЕРЁМ размер из объекта Telegram (НЕ len()!)

        # 🔹 Валидация размера (опционально)
        MAX_SIZE = 20 * 1024 * 1024  # 20 МБ
        if file_size and file_size > MAX_SIZE:
            await message.answer(f"❌ Файл слишком большой ({file_size / 1024 / 1024:.2f} МБ). Максимум 20 МБ")
            return

        # 🔹 Сохраняем file_id в FSM data
        async with state.proxy() as data:
            data['clip_video_file_id'] = video_file_id
            data['clip_file_size'] = file_size

        # 🔹 Переводим в состояние ожидания описания
        await ActionState.clip_waiting_desc.set()

        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("❌ Отмена", callback_data="clip_cancel")
        )

        await message.answer(
            "📝 **Добавьте описание к клипу**\n\n"
            "Напишите краткое описание или нажмите «Пропустить»:\n\n"
            "🔙 Нажмите «Отмена» в любой момент",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logging.info(f"🎬 Видео получено: {file_size / 1024 / 1024:.2f} МБ от @{message.from_user.username}")

    except Exception as e:
        logging.error(f"❌ receive_clip_video: {type(e).__name__}: {e}")
        await message.answer("❌ Ошибка обработки видео. Попробуйте ещё раз или /cancel")
        await state.finish()


# =========================
# 🔗 МЕТОД: ОТПРАВКА ССЫЛКИ
# =========================

@dp.callback_query_handler(lambda c: c.data == "clip_method_link")
async def clip_method_link(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал отправку ссылки"""
    try:
        await ActionState.clip_link_waiting_url.set()

        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("❌ Отмена", callback_data="clip_cancel")
        )

        await callback.message.edit_text(
            "🔗 **Отправка ссылки**\n\n"
            "📤 Загрузите видео в облако и отправьте ссылку:\n\n"
            "✅ **Поддерживаемые сервисы:**\n"
            "• Google Drive\n"
            "• Яндекс.Диск\n"
            "• Dropbox\n"
            "• Mega.nz\n"
            "• OneDrive\n\n"
            "⚠️ **Важно:**\n"
            "• Ссылка должна быть публичной\n"
            "• Не требовать логин/пароль\n"
            "• Проверьте в режиме инкогнито\n\n"
            "🔙 Нажмите «Отмена» в любой момент",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ clip_method_link: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.message_handler(state=ActionState.clip_link_waiting_url, content_types=types.ContentTypes.TEXT)
async def receive_clip_link_url(message: types.Message, state: FSMContext):
    """Получение ссылки на клип"""
    try:
        clip_url = message.text.strip()

        # 🔹 Валидация URL
        if not clip_url.startswith(('http://', 'https://')):
            await message.answer("❌ Это не похоже на ссылку. Отправьте URL, начинающийся с http:// или https://")
            return

        # 🔹 Сохраняем ссылку в FSM data (ВАЖНО: clip_drive_link!)
        async with state.proxy() as data:
            data['clip_drive_link'] = clip_url  # ← Исправлено!

        # 🔹 Переводим в состояние ожидания описания
        await ActionState.clip_link_waiting_desc.set()

        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("❌ Отмена", callback_data="clip_cancel")
        )

        await message.answer(
            "📝 **Добавьте описание к клипу**\n\n"
            "Напишите краткое описание или нажмите «Пропустить»:\n\n"
            "🔙 Нажмите «Отмена» в любой момент",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"❌ receive_clip_link_url: {e}")
        await message.answer("❌ Ошибка. Попробуйте ещё раз или /cancel")
        await state.finish()
# =========================
# 📝 ОПИСАНИЕ КЛИПА (универсальное)
# =========================

@dp.message_handler(state=ActionState.clip_waiting_desc)
async def receive_clip_description(message: types.Message, state: FSMContext):
    """Получение описания для файла"""
    await finalize_clip_submission(message, state)


@dp.message_handler(state=ActionState.clip_link_waiting_desc)
async def receive_clip_link_description(message: types.Message, state: FSMContext):
    """Получение описания для ссылки"""
    await finalize_clip_submission(message, state)


async def finalize_clip_submission(message: types.Message, state: FSMContext):
    """Финализация отправки клипа"""
    try:
        # ✅ Исправлено: добавлено 'data:' в конце строки
        async with state.proxy() as data:
            description = message.text if message.text != "Пропустить" else ""
            user_id = message.from_user.id

            # 🔹 Проверяем, какой тип клипа был отправлен
            clip_video_file_id = data.get('clip_video_file_id')  # Для видео-файла
            clip_drive_link = data.get('clip_drive_link')  # Для ссылки

            if clip_video_file_id:
                # 📁 Отправка видео-файлом
                logging.info(f"📁 Сохранение видео-файла: {clip_video_file_id}")
                await upload_video_to_drive(
                    user_id=user_id,
                    clip_type="video_file",
                    clip_file_id=clip_video_file_id,
                    description=description
                )
            elif clip_drive_link:
                # 🔗 Отправка ссылкой
                logging.info(f"🔗 Сохранение ссылки: {clip_drive_link}")
                await upload_video_to_drive(
                    user_id=user_id,
                    clip_type="link",
                    clip_url=clip_drive_link,
                    description=description
                )
            else:
                # ❌ Нет данных о клипе
                logging.error(f"❌ Нет данных о клипе у пользователя {user_id}")
                await message.answer("❌ Ошибка: нет данных о клипе. Начните заново.")
                await state.finish()
                return

            await message.answer("✅ Клип успешно отправлен на модерацию!")

        await state.finish()

    except Exception as e:
        logging.error(f"❌ finalize_clip_submission: {type(e).__name__}: {e}")
        await message.answer("❌ Ошибка отправки. Попробуйте ещё раз")
        await state.finish()
# =========================
# 🎬 АДМИН: МОДЕРАЦИЯ КЛИПОВ (ссылка на диск уже есть)
# =========================

@dp.callback_query_handler(lambda c: c.data.startswith("clip_approve_"))
async def approve_clip(callback: types.CallbackQuery):
    """Одобрение клипа — просто меняем статус"""
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        clip_id = callback.data.replace("clip_approve_", "")
        ws = get_clips_sheet()
        rows = ws.get_all_values()

        # Ищем клип
        row_idx = None
        user_tg_id = None
        drive_link = None

        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == clip_id:
                row_idx = idx
                user_tg_id = row[3]
                drive_link = row[4]
                break

        if not row_idx:
            await callback.answer("❌ Клип не найден", show_alert=True)
            return

        # Обновляем статус
        ws.update_cell(row_idx, 9, "одобрен")  # Статус
        ws.update_cell(row_idx, 10, get_msk_time().strftime("%d.%m.%Y %H:%M"))  # Дата одобрения
        ws.update_cell(row_idx, 11, callback.from_user.username or "admin")  # Кто одобрил

        # Уведомляем пользователя
        try:
            await bot.send_message(
                int(user_tg_id),
                f"✅ Ваш клип #{clip_id} одобрен! 🎉\n\n"
                f"🔗 Ссылка: {drive_link}\n\n"
                f"Спасибо за контент! 🎮"
            )
        except:
            pass  # Пользователь мог заблокировать бота

        await callback.message.edit_text(f"✅ Клип #{clip_id} одобрен!\n🔗 {drive_link}")
        await callback.answer()

    except Exception as e:
        logging.error(f"❌ approve_clip: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data.startswith("clip_reject_"))
async def reject_clip(callback: types.CallbackQuery):
    """Отклонение клипа + удаление с диска (опционально)"""
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        clip_id = callback.data.replace("clip_reject_", "")
        ws = get_clips_sheet()
        rows = ws.get_all_values()

        row_idx = None
        user_tg_id = None
        drive_file_id = None

        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == clip_id:
                row_idx = idx
                user_tg_id = row[3]
                drive_file_id = row[5]  # Drive File ID для удаления
                break

        if not row_idx:
            await callback.answer("❌ Клип не найден", show_alert=True)
            return

        # Опционально: удалить файл с диска при отклонении
        # if drive_file_id:
        #     from gdrive import get_drive_service
        #     service = get_drive_service()
        #     service.files().delete(fileId=drive_file_id).execute()

        # Обновляем статус
        ws.update_cell(row_idx, 9, "отклонён")

        # Уведомляем пользователя
        try:
            await bot.send_message(
                int(user_tg_id),
                f"❌ Ваш клип #{clip_id} не прошёл модерацию.\n"
                f"Попробуйте отправить другой момент! 🎮"
            )
        except:
            pass

        await callback.message.edit_text(f"❌ Клип #{clip_id} отклонён")
        await callback.answer()

    except Exception as e:
        logging.error(f"❌ reject_clip: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# =========================
# 🔇 МУТ ЧЕРЕЗ ОТВЕТ НА СООБЩЕНИЕ (ИСПРАВЛЕНО)
# =========================
@dp.message_handler(
    lambda msg: (
            msg.reply_to_message is not None and
            msg.text and
            msg.text.strip().lower().startswith(("мут ", "/мут "))
    ),
    content_types=types.ContentTypes.TEXT,
    state="*"  # Работает в любом состоянии
)
async def mute_via_reply(message: types.Message):
    try:
        # 🔹 Проверяем, что это команда мута
        text = message.text.strip().lower()
        if not (text.startswith("мут ") or text.startswith("/мут ") or text == "мут"):
            return

        # 🔹 Проверяем права отправителя
        moderator_id = message.from_user.id
        if not is_moderator(moderator_id):
            return

        # 🔹 Получаем пользователя, которому ответили
        replied_user = message.reply_to_message.from_user
        violator_id = replied_user.id
        violator_username = f"@{replied_user.username}" if replied_user.username else replied_user.full_name

        # 🔹 Парсим причину и время
        command_parts = message.text.strip().split(maxsplit=2)
        if len(command_parts) < 2:
            await message.answer("❌ Формат: `мут <причина> <время>`\nПример: `мут спам 10m`", parse_mode="Markdown")
            return

        reason = ""
        duration = ""

        if len(command_parts) == 2:
            second_part = command_parts[1]
            if re.match(r'^\d+[smhd]$', second_part.lower()):
                duration = second_part
                reason = "Нарушение правил"
            else:
                reason = second_part
                duration = "10m"
        else:
            reason = command_parts[1]
            duration = command_parts[2] if re.match(r'^\d+[smhd]$', command_parts[2].lower()) else "10m"

        # 🔹 Конвертируем длительность в секунды для Telegram API
        mute_seconds = parse_duration_to_seconds(duration)
        duration_readable = parse_duration(duration)

        # 🔹 Логируем в таблицу (до применения мута)
        moderator_nick = find_member_by_tg_id(moderator_id) or message.from_user.full_name
        violator_nick = find_member_by_tg_id(violator_id) or violator_username

        # 🔹 ПРИМЕНЯЕМ МУТ ЧЕРЕЗ TELEGRAM API ⚡
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=violator_id,
                permissions=types.ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False
                ),
                until_date=datetime.now(pytz.timezone("Europe/Moscow")) + timedelta(
                    seconds=mute_seconds) if mute_seconds > 0 else None
            )
            logging.info(f"✅ Мут применён: {violator_id} на {mute_seconds} сек в чате {message.chat.id}")
        except Exception as api_error:
            logging.error(f"❌ Ошибка Telegram API при муте: {api_error}")
            # Если бот не админ или нет прав — сообщаем об этом
            if "not enough rights" in str(api_error).lower() or "bot is not an administrator" in str(api_error).lower():
                await message.answer(
                    "❌ Ошибка: бот не имеет прав на мут!\nДобавьте бота в админы с правом «Ограничивать участников»")
                return
            elif "user is an administrator" in str(api_error).lower():
                await message.answer("❌ Нельзя мутить администратора чата")
                return

        # 🔹 Логируем в таблицу
        if not append_mute_log(violator_nick, violator_id, moderator_nick, moderator_id, reason, duration_readable):
            logging.warning("⚠️ Не удалось записать мут в таблицу")

        # 🔹 Отправляем отчёт в чат
        report_text = (
            f"🔇 <b>Мут выдан</b>\n\n"
            f"👤 Нарушитель: <code>{html_lib.escape(violator_username)}</code>\n"
            f"🛡 Модератор: <code>{html_lib.escape(moderator_nick)}</code>\n"
            f"⏱ Длительность: <code>{duration_readable}</code>\n"
            f"📝 Причина: <code>{html_lib.escape(reason)}</code>"
        )
        await message.answer(report_text, parse_mode="HTML")

        # 🔹 Логируем действие
        append_log("МУТ", moderator_nick, moderator_id, violator_nick)

        # 🔹 Уведомляем нарушителя в ЛС
        try:
            await bot.send_message(
                violator_id,
                f"🔇 Вам выдан мут в чате клана PET\n"
                f"🕒 Длительность: {duration_readable}\n"
                f"📝 Причина: {reason}\n"
                f"🛡 Модератор: {moderator_nick}",
                parse_mode="HTML"
            )
        except:
            pass  # Пользователь мог заблокировать бота

    except Exception as e:
        logging.error(f"❌ mute_via_reply: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при выдаче мута: {e}")


# =========================
# 🔤 ВСПОМОГАТЕЛЬНАЯ: Парсинг длительности в секунды
# =========================
def parse_duration_to_seconds(duration: str) -> int:
    """Конвертирует 10m/1h/2d в секунды для Telegram API"""
    import re
    match = re.match(r'^(\d+)([smhd])$', duration.lower())
    if not match:
        return 600  # дефолт 10 минут

    value, unit = int(match.group(1)), match.group(2)
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return value * multipliers.get(unit, 60)


# =========================
# 🔤 ВСПОМОГАТЕЛЬНАЯ: Парсинг длительности (для отображения)
# =========================
def parse_duration(duration: str) -> str:
    """Конвертирует 10m/1h/2d в человекочитаемый формат"""
    import re
    match = re.match(r'^(\d+)([smhd])$', duration.lower())
    if not match:
        return "10 минут"

    value, unit = int(match.group(1)), match.group(2)
    units = {
        's': ('секунд', 'секунду', 'секунды'),
        'm': ('минут', 'минуту', 'минуты'),
        'h': ('часов', 'час', 'часа'),
        'd': ('дней', 'день', 'дня')
    }

    if value == 1:
        return f"1 {units[unit][1]}"
    elif 2 <= value <= 4:
        return f"{value} {units[unit][2]}"
    else:
        return f"{value} {units[unit][0]}"
# =========================
# 📝 РЕГИСТРАЦИЯ
# =========================
@dp.callback_query_handler(lambda c: c.data == "apply_start")
async def apply_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        apps = get_applications(status="ожидает")
        if any(app[4] == str(user_id) for app in apps):
            await callback.answer("⚠️ У вас уже есть активная заявка!", show_alert=True)
            return
        await state.update_data(tg_username=callback.from_user.username or callback.from_user.full_name, tg_id=user_id)
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🆕 Я новенький", callback_data="reg_type_new"),
            InlineKeyboardButton("👤 Я уже в клане", callback_data="reg_type_existing")
        )
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
        await callback.message.edit_text("🔍 Выберите вариант:\n🆕 Новенький — подайте заявку на вступление\n👤 Уже в клане — привяжите аккаунт к существующему нику", reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ apply_start: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query_handler(
    lambda c: c.data == "reg_type_new",
    state="*"
)
async def reg_type_new(callback: types.CallbackQuery, state: FSMContext):
    try:
        await ActionState.reg_rules.set()

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✅ Согласен с правилами", callback_data="rules_accept"),
            InlineKeyboardButton("❌ Отмена", callback_data="apply_start")
        )

        await callback.message.edit_text(
            "📜 Правила клана PET\n"
            "1️⃣ Уважение ко всем участникам\n"
            "2️⃣ Запрет на читы\n"
            "3️⃣ Активность в клане\n"
            "4️⃣ Выполнение приказов\n"
            "5️⃣ Конфиденциальность\n\n"
            "⚠️ Нарушение = предупреждение или кик!\n"
            "Полный список правил: https://telegra.ph/Pravila-klana-03-01-3 Просьба внимательно ознакомиться! Дабы потом не задавть лищние вопросы\n"
            "Согласны?",
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ reg_type_new: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)
@dp.callback_query_handler(
    lambda c: c.data == "rules_accept",
    state=ActionState.reg_rules
)
async def rules_accepted(callback: types.CallbackQuery, state: FSMContext):
    try:
        await ActionState.reg_steam_nick.set()

        await callback.message.edit_text(
            "🆕 Введите ваш никнейм в Steam (как в игре):\n"
            "Пример: [PET] КИРЮХА"
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ rules_accepted: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.message_handler(state=ActionState.reg_steam_nick)
async def reg_save_steam_nick(message: types.Message, state: FSMContext):
    try:
        steam_nick = message.text.strip()

        if len(steam_nick) < 2:
            await message.answer("❌ Ник слишком короткий. Введите корректный Steam ник:")
            return

        await state.update_data(steam_nick=steam_nick)
        await ActionState.reg_steam_id.set()

        await message.answer(
            "🎮 Введите Steam ID (64-bit):\n"
            "Пример: 76561198984240881\n"
            "Как узнать: https://steamid.io/"
        )

    except Exception as e:
        logging.error(f"❌ reg_save_steam_nick: {e}", exc_info=True)

@dp.message_handler(state=ActionState.reg_steam_id)
async def reg_save_steam_id(message: types.Message, state: FSMContext):
    try:
        steam_id = message.text.strip()

        if not steam_id.isdigit() or len(steam_id) < 17:
            await message.answer("❌ Неверный формат Steam ID. Попробуйте ещё раз:")
            return

        await state.update_data(steam_id=steam_id)
        await ActionState.reg_confirm.set()

        data = await state.get_data()

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✅ Подтвердить заявку", callback_data="app_submit"),
            InlineKeyboardButton("❌ Изменить", callback_data="reg_type_new")
        )

        await message.answer(
            f"📋 Проверьте данные:\n"
            f"🎮 Ник: <code>{data['steam_nick']}</code>\n"
            f"🆔 Steam ID: <code>{steam_id}</code>\n"
            f"👤 TG: <code>{message.from_user.full_name}</code>\n\n"
            f"Всё верно?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"❌ reg_save_steam_id: {e}", exc_info=True)

@dp.callback_query_handler(
    lambda c: c.data == "app_submit",
    state=ActionState.reg_confirm
)
async def app_submit(callback: types.CallbackQuery, state: FSMContext):
    try:
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
                kb = InlineKeyboardMarkup(row_width=2)
                kb.add(
                    InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
                )

                await bot.send_message(
                    admin_id,
                    f"📬 Новая заявка!\n"
                    f"🆔 #{app_id}\n"
                    f"🎮 <code>{steam_nick}</code>\n"
                    f"🆔 <code>{steam_id}</code>\n"
                    f"👤 {tg_username}\n"
                    f"🆔 <code>{tg_id}</code>",
                    reply_markup=kb,
                    parse_mode="HTML"
                )

            except Exception as e:
                logging.error(f"❌ Ошибка уведомления админа: {e}")

        await callback.message.edit_text(
            f"✅ Заявка отправлена!\n"
            f"📋 ID: <code>#{app_id}</code>\n"
            f"Ожидайте решения модераторов!",
            reply_markup=main_menu(tg_id, has_pending_app=True),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ app_submit: {e}", exc_info=True)
        await callback.answer("❌ Ошибка отправки", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "reg_type_existing", state="*")
async def reg_type_existing(callback: types.CallbackQuery, state: FSMContext):
    try:
        await ActionState.reg_select_existing.set()

        ws = sheet.worksheet("участники клана")
        rows = ws.get_all_values()[1:]

        unregistered = []
        for row in rows:
            if len(row) >= 1 and row[0].strip():
                tg_id_in_table = row[8].strip() if len(row) > 8 else ""
                if not tg_id_in_table:
                    unregistered.append(row[0].strip())

        if not unregistered:
            keyboard = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Назад", callback_data="apply_start")
            )
            await callback.message.edit_text(
                "✅ Все участники уже зарегистрированы!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await state.update_data(unregistered_list=unregistered)

        keyboard = InlineKeyboardMarkup(row_width=2)
        for idx, nick in enumerate(unregistered[:30]):
            keyboard.insert(
                InlineKeyboardButton(nick, callback_data=f"reg_sel_{idx}")
            )

        keyboard.add(
            InlineKeyboardButton("🔙 Назад", callback_data="apply_start")
        )

        await callback.message.edit_text(
            f"👤 Выберите ваш никнейм\n"
            f"Найдено {len(unregistered)} участников без регистрации:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ reg_type_existing: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка", show_alert=True)


@dp.callback_query_handler(
    lambda c: c.data.startswith("reg_sel_"),
    state=ActionState.reg_select_existing
)
async def reg_select_existing(callback: types.CallbackQuery, state: FSMContext):
    try:
        logging.info(f"🔥 CALLBACK RECEIVED: {callback.data}")

        idx_str = callback.data.replace("reg_sel_", "", 1).strip()

        if not idx_str.isdigit():
            await callback.answer("❌ Ошибка индекса", show_alert=True)
            return

        idx = int(idx_str)

        data = await state.get_data()
        unregistered = data.get("unregistered_list", [])

        # Если вдруг список потерялся — перезагружаем
        if not unregistered:
            ws = sheet.worksheet("участники клана")
            rows = ws.get_all_values()[1:]

            for row in rows:
                if len(row) >= 1 and row[0].strip():
                    tg_id_in_table = row[8].strip() if len(row) > 8 else ""
                    if not tg_id_in_table:
                        unregistered.append(row[0].strip())

            await state.update_data(unregistered_list=unregistered)

        if idx >= len(unregistered):
            await callback.answer("❌ Ник не найден", show_alert=True)
            return

        nickname = unregistered[idx]
        await state.update_data(selected_nick=nickname)

        await ActionState.reg_existing_confirm.set()

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✅ Да, это я!", callback_data="reg_existing_yes"),
            InlineKeyboardButton("❌ Нет, другой", callback_data="reg_type_existing")
        )

        safe_nickname = html_lib.escape(nickname)

        await callback.message.edit_text(
            f"🔍 Подтверждение\n"
            f"Вы выбираете: <b>{safe_nickname}</b>\n"
            f"Это правильный ник?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ reg_select_existing: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при выборе ника", show_alert=True)

@dp.callback_query_handler(
    lambda c: c.data == "reg_existing_yes",
    state=ActionState.reg_existing_confirm
)
async def reg_existing_confirm(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        nickname = data.get("selected_nick")
        tg_username = data.get("tg_username")
        tg_id = data.get("tg_id")

        if not nickname:
            await callback.answer("❌ Ошибка: ник не выбран", show_alert=True)
            return

        existing = find_member_by_tg_id(tg_id)
        if existing:
            safe_existing = html_lib.escape(existing)
            await callback.message.edit_text(
                f"⚠️ Ваш TG уже привязан!\n"
                f"Вы зарегистрированы как: {safe_existing}",
                reply_markup=main_menu(tg_id, is_registered=True),
                parse_mode="HTML"
            )
            await state.finish()
            await callback.answer()
            return

        if update_member_tg_data(nickname, tg_username, tg_id):
            append_log("РЕГИСТРАЦИЯ_УЧАСТНИК", tg_username, tg_id, nickname)

            safe_nick = html_lib.escape(nickname)

            await callback.message.edit_text(
                f"✅ Регистрация завершена!\n"
                f"Вы привязаны к: {safe_nick}\n"
                f"Теперь доступны все функции!",
                reply_markup=main_menu(tg_id, is_registered=True),
                parse_mode="HTML"
            )

            await state.finish()
        else:
            await callback.answer("❌ Ошибка обновления данных", show_alert=True)

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ reg_existing_confirm: {e}", exc_info=True)
        await callback.answer("❌ Внутренняя ошибка регистрации", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "app_status")
async def app_status(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        apps = get_applications()
        user_app = next((app for app in apps if app[4] == str(user_id)), None)
        if not user_app:
            await callback.answer("❌ У вас нет заявок", show_alert=True)
            return
        status_emoji = {"ожидает": "🟡", "принят": "🟢", "отклонен": "🔴"}.get(user_app[6], "⚪")
        text = f"📋 Статус заявки\n🆔 #{user_app[0]}\n🎮 `{user_app[1]}`\n🕒 {user_app[5]}\n{status_emoji} {user_app[6]}\n"
        if user_app[6] == "принят":
            text += f"🎉 Поздравляем! Ссылка: {GROUP_LINK}"
        elif user_app[6] == "отклонен":
            text += "❌ Заявка отклонена."
        else:
            text += "⏳ На рассмотрении."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu")), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ app_status: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# === В начало bot.py, после других импортов ===
import re
from datetime import datetime
from krestgg_parser import parser as krest_parser

import traceback
import re
from datetime import datetime
from krestgg_parser import parser as krest_parser


@dp.message_handler(commands=['pet_online', 'пет_онлайн', 'клан_онлайн'])
async def cmd_pet_online(message: types.Message):
    status = await message.answer("🔍 Сканирую сервера Крестов...")

    try:
        # Получаем данные от парсера
        data = await krest_parser.get_pet_online_by_server(force_refresh=True)

        # 🔧 ИСПРАВЛЕНО: полная проверка на пустой результат
        if not data or not any(data.values()):
            await status.edit_text("🔴 Сейчас нет игроков [PET] в сети или сайт не ответил.")
            return

        lines = ["🟢 <b>Клан [PET] по серверам:</b>\n"]
        total = 0

        for server, players in data.items():
            # Чистим название сервера: [RU][AAS+] Кресты → AAS+
            srv_clean = re.sub(r'\[RU\]\s*', '', server, flags=re.I).strip()
            srv_clean = re.sub(r'\s*Кресты$', '', srv_clean, flags=re.I).strip()

            count = len(players)
            if count == 0:
                continue

            total += count
            lines.append(f"🎮 <b>{srv_clean}</b> ({count}):")

            # Группируем по 5 ников в строку
            for i in range(0, count, 5):
                chunk = players[i:i + 5]
                # Убираем теги [PET]/[PETt]/[PETs], оставляем только ник
                clean_nicks = [
                    re.sub(r'\[(?:PET|PETt|PETs)\]\s*', '', p, flags=re.I).strip()
                    for p in chunk
                ]
                # Форматируем: • ник1  • ник2  • ник3
                nick_str = "  • ".join(f"<code>{n}</code>" for n in clean_nicks if n)
                if nick_str:
                    lines.append("  • " + nick_str)
            lines.append("")  # пустая строка между серверами

        lines.append(f"📊 <i>Всего онлайн: {total} | Обновлено: {get_msk_time().strftime('%H:%M:%S')}</i>")

        # Отправляем сообщение (если текст слишком длинный — разбиваем)
        full_text = "\n".join(lines)
        if len(full_text) > 4096:
            # Telegram лимит: 4096 символов на сообщение
            await status.edit_text(full_text[:4090] + "\n\n...")
        else:
            await status.edit_text(full_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"❌ Ошибка /pet_online:\n{traceback.format_exc()}")
        await status.edit_text(
            "⚠️ Произошла ошибка при опросе серверов.\n"
            "Проверь логи или попробуй позже.",
            parse_mode="HTML"
        )
# =========================
# 📬 АДМИН-ПАНЕЛЬ ЗАЯВОК
# =========================
@dp.callback_query_handler(
    lambda c: c.data == "applications_menu",
    state="*"
)
async def applications_menu(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        apps = get_applications(status="ожидает")

        keyboard = InlineKeyboardMarkup(row_width=1)

        if not apps:
            keyboard.add(
                InlineKeyboardButton("📭 Нет заявок", callback_data="none")
            )
        else:
            for app in apps:
                keyboard.add(
                    InlineKeyboardButton(
                        f"📬 #{app[0]} | {app[1]}",
                        callback_data=f"app_view_{app[0]}"
                    )
                )

        keyboard.add(
            InlineKeyboardButton("🟢 Принятые", callback_data="apps_accepted"),
            InlineKeyboardButton("🔴 Отклонённые", callback_data="apps_rejected"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text(
            f"📬 Заявки\n🟡 Ожидает: {len(apps)}",
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ applications_menu: {e}", exc_info=True)

@dp.callback_query_handler(
    lambda c: c.data.startswith("app_view_"),
    state="*"
)
async def app_view(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return

        app_id = callback.data.replace("app_view_", "")
        app = get_application_by_id(app_id)

        if not app:
            await callback.answer("❌ Не найдено", show_alert=True)
            return

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
        )
        kb.add(
            InlineKeyboardButton("🔙 Назад", callback_data="applications_menu")
        )

        text = (
            f"📬 Заявка #{app['id']}\n"
            f"🎮 <code>{app['nick']}</code>\n"
            f"🆔 <code>{app['steam_id']}</code>\n"
            f"👤 {app['tg_username']}\n"
            f"🆔 <code>{app['tg_id']}</code>\n"
            f"🕒 {app['date']}\n"
            f"🟡 {app['status']}"
        )

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        logging.error(f"❌ app_view: {e}", exc_info=True)
@dp.callback_query_handler(
    lambda c: c.data.startswith("app_accept_"),
    state="*"
)
async def app_accept(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return

        app_id = callback.data.replace("app_accept_", "")
        app = get_application_by_id(app_id)

        if not app:
            await callback.answer("❌ Не найдено", show_alert=True)
            return

        update_application_status(app_id, "принят")

        if add_new_member(app['nick'], app['steam_id'], app['tg_username'], app['tg_id']):
            try:
                await bot.send_message(
                    int(app['tg_id']),
                    f"🎉 Заявка принята!\nДобро пожаловать в PET!\n🔗 {GROUP_LINK}"
                )
            except:
                pass

            append_log(
                "ЗАЯВКА_ПРИНЯТА",
                callback.from_user.full_name,
                callback.from_user.id,
                app['nick']
            )

            await callback.answer("✅ Принято! Участник добавлен", show_alert=True)
        else:
            await callback.answer("⚠️ Уже существует", show_alert=True)

        await applications_menu(callback)

    except Exception as e:
        logging.error(f"❌ app_accept: {e}", exc_info=True)
@dp.callback_query_handler(
    lambda c: c.data.startswith("app_reject_"),
    state="*"
) #123
async def app_reject(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return

        app_id = callback.data.replace("app_reject_", "")
        app = get_application_by_id(app_id)

        if not app:
            await callback.answer("❌ Не найдено", show_alert=True)
            return

        update_application_status(app_id, "отклонен")

        try:
            await bot.send_message(
                int(app['tg_id']),
                "❌ Заявка отклонена\nПопробуйте через 7 дней."
            )
        except:
            pass

        append_log(
            "ЗАЯВКА_ОТКЛОНЕНА",
            callback.from_user.full_name,
            callback.from_user.id,
            app['nick']
        )

        await callback.answer("❌ Отклонено", show_alert=True)
        await applications_menu(callback)

    except Exception as e:
        logging.error(f"❌ app_reject: {e}", exc_info=True)
@dp.callback_query_handler(
    lambda c: c.data in ["apps_accepted", "apps_rejected"],
    state="*"
)
async def apps_archive(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return

        is_accepted = callback.data == "apps_accepted"
        status = "принят" if is_accepted else "отклонен"

        apps = get_applications(status=status)

        kb = InlineKeyboardMarkup(row_width=1)
        for app in apps[:10]:
            kb.add(
                InlineKeyboardButton(
                    f"#{app[0]} | {app[1]}",
                    callback_data=f"app_view_{app[0]}"
                )
            )

        kb.add(
            InlineKeyboardButton("🔙 Назад", callback_data="applications_menu")
        )

        await callback.message.edit_text(
            f"{'🟢 Принятые' if is_accepted else '🔴 Отклонённые'}\n"
            f"Всего: {len(apps)}",
            reply_markup=kb
        )

        await callback.answer()

    except Exception as e:
        logging.error(f"❌ apps_archive: {e}", exc_info=True)


# =========================
# 📊 SQSTAT PARSER
# =========================
async def fetch_sqstat_profile(steam_id: str) -> dict | None:
    """Парсит статистику с breaking.proxy.sqstat.ru/player/{steam_id}"""
    import aiohttp
    from bs4 import BeautifulSoup
    import re

    url = f"https://breaking.proxy.sqstat.ru/player/{steam_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0"
            }) as response:
                if response.status != 200:
                    return None
                html = await response.text()

        soup = BeautifulSoup(html, 'lxml')
        stats = {}
        text_content = soup.get_text(separator='\n', strip=True)
        lines = [l.strip() for l in text_content.split('\n') if l.strip()]

        # 🔹 Улучшенная функция поиска числовых значений
        def find_numeric_value(label: str, allow_percent: bool = False):
            """Ищет числовое значение после метки, игнорируя буквы типа 'м'"""
            # Паттерн: метка + разделители + число (с запятыми/точками/процентами)
            percent_pattern = r'[\d\s,]+\.?\d*%' if allow_percent else r'[\d\s,]+\.?\d*'
            pattern = rf'{re.escape(label)}\s*[:\s\n]*\s*({percent_pattern})'
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                # Очищаем и проверяем, что это действительно число
                cleaned = re.sub(r'[^\d.,%]', '', raw)
                if cleaned and (cleaned.replace('.', '').replace(',', '').replace('%', '').isdigit()):
                    return cleaned.replace(',', '.')  # нормализуем разделитель
            return None

        # 🔹 Функция для поиска любого значения (если нужно не только число)
        def find_any_value(label: str):
            pattern = rf'{re.escape(label)}\s*[:\s\n]*\s*([^\n]+?)(?:\n|$)'
            match = re.search(pattern, text_content, re.IGNORECASE)
            return match.group(1).strip() if match and match.group(1).strip() else None

        # 🔹 Ключевые метрики (только числа)
        stats['kd'] = find_numeric_value('К/Д')  # может быть 0.69
        stats['winrate'] = find_numeric_value('Винрейт', allow_percent=True)  # 54.1%
        stats['kills'] = find_numeric_value('УБИЙСТВА')
        stats['deaths'] = find_numeric_value('СМЕРТИ')
        stats['damage'] = find_numeric_value('УРОН')
        stats['revives'] = find_numeric_value('ПОДНЯТИЯ')
        stats['matches'] = find_numeric_value('МАТЧЕЙ')
        stats['wins'] = find_numeric_value('ПОБЕД')
        stats['losses'] = find_numeric_value('ПРОИГРЫШЕЙ')

        # 🔹 Время в игре (может быть в минутах или формате "2645")
        raw_playtime = find_numeric_value('ОНЛАЙН')
        if raw_playtime:
            try:
                total_minutes = int(float(raw_playtime.replace(',', '.')))
                hours = total_minutes // 60
                minutes = total_minutes % 60
                stats['playtime'] = f"{hours}ч {minutes:02d}м" if hours > 0 else f"{minutes}м"
            except:
                stats['playtime'] = raw_playtime  # fallback если не получилось конвертировать
        else:
            # Пробуем найти время в другом формате (например "44ч 05м")
            alt_time = find_any_value('ОНЛАЙН')
            if alt_time and any(c.isdigit() for c in alt_time):
                stats['playtime'] = alt_time[:20]  # обрезаем если слишком длинное

        # 🔹 Топ оружие (ищем строки с названием оружия + числом убийств)
        weapons = []
        weapon_names = ['M16A4', 'M4A1', 'AK-12', 'AKM', 'SCAR-H', 'QBZ-03', 'AUG-A3', 'MP7', 'M249', 'PKM']
        for line in lines:
            for wname in weapon_names:
                if wname.lower() in line.lower():
                    # Ищем число в этой же строке или следующей
                    nums = re.findall(r'[\d]+', line)
                    if nums:
                        weapons.append({'name': wname, 'kills': nums[-1]})
                    break
            if len(weapons) >= 3:
                break
        stats['top_weapons'] = weapons

        # 🔹 Последние матчи (карты)
        matches = []
        seen_maps = set()
        for line in lines:
            # Фильтр по известным картам Squad
            if any(m in line for m in
                   ['Gorodok', 'Breakwater', 'Lashkar', 'Khanji', 'Tallil', 'Yehorivka', 'Fallujah']):
                if line[:30] not in seen_maps:  # избегаем дублей
                    result = "⚪"
                    # Ищем результат в соседних строках
                    idx = lines.index(line) if line in lines else -1
                    if idx >= 0:
                        context = ' '.join(lines[max(0, idx - 2):min(len(lines), idx + 3)]).lower()
                        if any(x in context for x in ['победа', 'да', 'выигрыш']):
                            result = "✅"
                        elif any(x in context for x in ['пораж', 'нет', 'проигр']):
                            result = "❌"
                    matches.append({'map': line[:30], 'result': result})
                    seen_maps.add(line[:30])
            if len(matches) >= 3:
                break
        stats['recent_matches'] = matches

        return stats

    except Exception as e:
        logging.error(f"❌ sqstat parse error: {e}")
        return None
            # Следующий элемент - количество убийств
# =========================
# 👤 ПРОФИЛЬ
# =========================
@dp.callback_query_handler(lambda c: c.data == "my_profile")
async def my_profile(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        await callback.answer()

        # Проверка регистрации
        existing_nick = find_member_by_tg_id(user_id)
        if not existing_nick:
            await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
            return

        info = get_member_info(existing_nick)
        if not info:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return

        # Базовая информация
        status_emoji = "✅" if info['desirable'] == "желателен" else "❌"
        safe_nick = html_lib.escape(info['nick'])
        steam_id = info.get('steam_id', 'N/A')

        # Формируем основную часть профиля
        text = f"👤 Ваш профиль\n"
        text += f"🎮 {safe_nick}\n"
        text += f"🆔 `{steam_id}`\n"
        text += f"🎖 {info['role']}\n"
        text += f"⚠️ {info['warns']}\n"
        text += f"👏 {info['praises']}\n"
        text += f"📊 {info['score']}\n"
        text += f"📌 {status_emoji} {info['desirable']}\n"
        text += f"🆔 `{user_id}`"

        # Если есть валидный Steam ID — пробуем подгрузить sqstat
        if steam_id and steam_id != 'N/A' and steam_id.isdigit():
            text += "\n\n🔄 <i>Загружаю статистику с серверов...</i>"
            loading_msg = await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")

            sqstats = await fetch_sqstat_profile(steam_id)

            if sqstats:
                sq_text = f"\n\n🌐 <b>Статистика с сервера:</b>\n"

                # K/D и Винрейт в одну строку
                kd = sqstats.get('kd', '0')
                wr = sqstats.get('winrate', '')
                sq_text += f"📊 K/D: <code>{kd}</code>"
                if wr:
                    sq_text += f" | 🏆 WR: <code>{wr}</code>"
                sq_text += "\n"

                # Статы в 2 колонки для компактности
                stats_row1 = []
                if sqstats.get('kills'): stats_row1.append(f"⚔️ {sqstats['kills']}")
                if sqstats.get('deaths'): stats_row1.append(f"💀 {sqstats['deaths']}")
                if stats_row1:
                    sq_text += f"{'  '.join(stats_row1)}\n"

                stats_row2 = []
                if sqstats.get('damage'): stats_row2.append(f"💥 {sqstats['damage']} урона")
                if sqstats.get('revives'): stats_row2.append(f"🩹 {sqstats['revives']} поднятий")
                if stats_row2:
                    sq_text += f"{'  '.join(stats_row2)}\n"

                if sqstats.get('playtime'):
                    sq_text += f"⏱ В игре: <code>{sqstats['playtime']}</code>\n"

                # Матчи
                if sqstats.get('matches'):
                    wins = sqstats.get('wins', '0')
                    losses = sqstats.get('losses', '0')
                    sq_text += f"🎮 Матчей: <code>{sqstats['matches']}</code> | ✅ {wins} | ❌ {losses}\n"

                # Топ оружие
                weapons = sqstats.get('top_weapons', [])
                if weapons:
                    sq_text += f"\n🔫 <b>Топ оружие:</b>\n"
                    for w in weapons:
                        sq_text += f"• {html_lib.escape(w['name'])}: <code>{w['kills']}</code>\n"

                # Последние матчи
                matches = sqstats.get('recent_matches', [])
                if matches:
                    sq_text += f"\n🗺 <b>Последние карты:</b>\n"
                    for m in matches[:3]:
                        sq_text += f"{m['result']} {html_lib.escape(m['map'])}\n"

                text = text.replace("\n\n🔄 <i>Загружаю статистику с серверов...</i>", "") + sq_text
            else:
                text = text.replace("\n\n🔄 <i>Загружаю статистику с серверов...</i>", "")
                text += f"\n\n⚠️ <i>Не удалось загрузить статистику</i>"
                text += f"\n🔗 <a href='https://breaking.proxy.sqstat.ru/player/{steam_id}'>Открыть на sqstat</a>"

            # Финальное обновление сообщения
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(InlineKeyboardButton("📜 Мои преды", callback_data="view_preds"))
            keyboard.add(InlineKeyboardButton("👏 Мои похвалы", callback_data="view_praises"))
            keyboard.row(
                InlineKeyboardButton("🔄 Обновить", callback_data="my_profile"),
                InlineKeyboardButton("🌐 Sqstat", url=f"https://breaking.proxy.sqstat.ru/player/{steam_id}")
            )
            keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

            await loading_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            # Нет валидного Steam ID — показываем профиль без sqstat
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton("📜 Мои преды", callback_data="view_preds"))
            keyboard.add(InlineKeyboardButton("👏 Мои похвалы", callback_data="view_praises"))
            keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

            text += f"\n\n⚠️ <i>Steam ID не указан или некорректен</i>"
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logging.error(f"❌ my_profile: {e}")
        await callback.answer("❌ Ошибка загрузки профиля", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "view_preds")
async def view_preds(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        if not existing_nick:
            await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
            return

        preds = get_member_preds(existing_nick)
        safe_nick = html_lib.escape(existing_nick)

        if not preds:
            text = f"📜 История предупреждений: {safe_nick}\n📭 Записей не найдено."
        else:
            text = f"📜 История предупреждений: {safe_nick}\n\n"
            for row in preds:
                # row: [member, reason, date]
                reason = html_lib.escape(row[1] if len(row) > 1 else "Без причины")
                date = html_lib.escape(row[2] if len(row) > 2 else "?")
                text += f"📅 {date} | ⚠️ {reason}\n"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="my_profile"))

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ view_preds: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "view_praises")
async def view_praises(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        if not existing_nick:
            await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
            return

        praises = get_member_praises(existing_nick)
        safe_nick = html_lib.escape(existing_nick)

        if not praises:
            text = f"👏 История похвал: {safe_nick}\n📭 Записей не найдено."
        else:
            text = f"👏 История похвал: {safe_nick}\n\n"
            for row in praises:
                # row: [member, from_user, reason, date]
                from_user = html_lib.escape(row[1] if len(row) > 1 else "Аноним")
                reason = html_lib.escape(row[2] if len(row) > 2 else "Без причины")
                date = html_lib.escape(row[3] if len(row) > 3 else "?")
                text += f"📅 {date} | 👤 {from_user} | 👏 {reason}\n"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="my_profile"))

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ view_praises: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# =========================
# 🎬 ОТПРАВКА КЛИПОВ (с Google Drive)
# =========================

# =========================
# 📹 ОТПРАВКА КЛИПА — ВЫБОР СПОСОБА
# =========================


# =========================
# 📋 КЛАН
# =========================
@dp.callback_query_handler(lambda c: c.data == "clan_list")
async def clan_list(callback: types.CallbackQuery):
    try:
        members = get_clan_members()
        kb = InlineKeyboardMarkup(row_width=2)
        for m in members:
            kb.add(InlineKeyboardButton(m, callback_data=f"member_{m[:50]}"))
        kb.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text("📋 Выберите участника:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ clan_list: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("member_"))
async def member_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        member = callback.data.replace("member_", "", 1)
        await state.update_data(member=member)
        is_admin = callback.from_user.id in ADMINS
        info = get_member_info(member) if is_admin else None

        kb = InlineKeyboardMarkup()

        # Кнопки только для админов
        if is_admin:
            kb.add(
                InlineKeyboardButton("📜 История предов", callback_data=f"view_member_preds_{member[:40]}"),
                InlineKeyboardButton("👏 История похвал", callback_data=f"view_member_praises_{member[:40]}")
            )
            kb.add(InlineKeyboardButton("⚠ Пред", callback_data="action_pred"))
            kb.add(InlineKeyboardButton("🔔 Вызвать в суд", callback_data="action_court"))  # 🆕
        if info:
            emoji = "✅ " if info['desirable'] == "желателен" else "❌ "
            safe_nick = html_lib.escape(info['nick'])
            text = f"👤 Карточка: {safe_nick}\n🎮 Steam: `{info['steam_id']}`\n🎖 Роль: {info['role']}\n⚠️ Предупреждения: {info['warns']}\n👏 Похвалы: {info['praises']}\n📊 Рейтинг: {info['score']}\n📌 Статус: {emoji}{info['desirable']}\nВыберите действие:"
        else:
            safe_member = html_lib.escape(member)
            text = f"⚠️ Участник {safe_member}\nИнформация не найдена.\nВыберите действие:"

        # Общие кнопки
        kb.add(
            InlineKeyboardButton("👏 Похвала", callback_data="action_praise"),
            InlineKeyboardButton("⚖ Жалоба", callback_data="action_complaint"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ member_selected: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("view_member_preds_"))
async def view_member_preds(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        member = callback.data.replace("view_member_preds_", "", 1)
        preds = get_member_preds_history(member)
        safe_member = html_lib.escape(member)

        if not preds:
            text = f"📜 История предупреждений: {safe_member}\n📭 Записей не найдено."
        else:
            text = f"📜 История предупреждений: {safe_member}\n\n"
            for row in preds:
                reason = html_lib.escape(row[1] if len(row) > 1 else "Без причины")
                date = html_lib.escape(row[2] if len(row) > 2 else "?")
                text += f"📅 {date} | ⚠️ {reason}\n"

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Назад", callback_data=f"member_{member[:40]}")
        )

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ view_member_preds: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data.startswith("view_member_praises_"))
async def view_member_praises(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        member = callback.data.replace("view_member_praises_", "", 1)
        praises = get_member_praises_history(member)
        safe_member = html_lib.escape(member)

        if not praises:
            text = f"👏 История похвал: {safe_member}\n📭 Записей не найдено."
        else:
            text = f"👏 История похвал: {safe_member}\n\n"
            for row in praises:
                from_user = html_lib.escape(row[1] if len(row) > 1 else "Аноним")
                reason = html_lib.escape(row[2] if len(row) > 2 else "Без причины")
                date = html_lib.escape(row[3] if len(row) > 3 else "?")
                text += f"📅 {date} | 👤 {from_user} | 👏 {reason}\n"

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Назад", callback_data=f"member_{member[:40]}")
        )

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ view_member_praises: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
@dp.callback_query_handler(lambda c: c.data.startswith("action_"))
async def action_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        action = callback.data.replace("action_", "")

        # 🆕 Логика для вызова в суд
        if action == "court":
            await ActionState.waiting_court_time.set()
            await callback.message.answer(
                "🔔 <b>Вызов в суд</b>\n\n"
                "📅 Введите дату и время проведения:\n"
                "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
                "Пример: <code>20.04.2026 20:00</code>\n\n"
                "🔙 /cancel для отмены",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await state.update_data(action=action)
        await ActionState.waiting_reason.set()
        await callback.message.answer("📝 Опиши причину (или /cancel):" if action == "complaint" else "📝 Напиши причину (или /cancel):")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ action_selected: {e}")


@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        member, action = data.get("member"), data.get("action")
        user = message.from_user
        username = f"@{user.username}" if user.username else user.full_name
        user_id = user.id

        if action == "pred":
            if user_id not in ADMINS:
                await message.answer("❌ Нет прав", reply_markup=main_menu(user_id))
                await state.finish()  # ✅ Обязательно сбрасываем состояние
                return

            append_pred(member, message.text)
            append_log("ПРЕД", username, user_id, member)

            existing_nick = find_member_by_tg_id(user_id)
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)

            # ✅ Отправляем новое сообщение с меню, но явно завершаем FSM
            await message.answer(
                "⚠ Пред записан ✅",
                reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending)
            )
            await state.finish()  # ✅ КЛЮЧЕВОЕ: сброс состояния!
            return

        elif action == "praise":
            existing_nick = find_member_by_tg_id(user_id)
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)

            sender_nick = find_member_by_tg_id(user_id) or username
            if member and sender_nick and member.lower() == sender_nick.lower():
                await message.answer("❌ Нельзя отправить похвалу самому себе!",reply_markup=main_menu(user_id, is_registered=(existing_nick is not None),has_pending_app=has_pending))
                await state.finish()
                return
            append_praise(member, username, message.text)
            append_log("ПОХВАЛА", username, user_id, member)

            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)

            await message.answer(
                "👏 Похвала записана ✅",
                reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending)
            )
            await state.finish()  # ✅ Сброс состояния
            return


        elif action == "complaint":

            add_complaint(username, user_id, member, message.text)

            append_log("ЖАЛОБА", username, user_id, member)

            # 🆕 УВЕДОМЛЕНИЕ АДМИНАМ О НОВОЙ ЖАЛОБЕ

            try:

                # Получаем актуальные данные, чтобы вычислить индекс новой строки

                rows = get_complaints()

                new_complaint_idx = len(rows) - 2  # -2 т.к. строка 0 = заголовок

                kb = InlineKeyboardMarkup().add(

                    InlineKeyboardButton("🔍 Открыть жалобу", callback_data=f"complaint_{new_complaint_idx}")

                )

                notify_text = (

                    f"⚖️ <b>Новая жалоба!</b>\n\n"

                    f"👤 От: {username}\n"

                    f"🎯 На: <code>{member}</code>\n"

                    f"📝 Причина: {html_lib.escape(message.text)}"

                )

                for admin_id in ADMINS:

                    try:

                        await bot.send_message(admin_id, notify_text, reply_markup=kb, parse_mode="HTML")

                    except Exception as e:

                        logging.warning(f"❌ Не удалось уведомить админа {admin_id}: {e}")

            except Exception as e:

                logging.error(f"❌ Ошибка отправки уведомления админам: {e}")

            # Остальной код без изменений

            existing_nick = find_member_by_tg_id(user_id)

            apps = get_applications(status="ожидает")

            has_pending = any(app[4] == str(user_id) for app in apps)

            await message.answer(

                "⚖ Жалоба отправлена ✅",

                reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending)

            )

            await state.finish()

            return

    except Exception as e:
        logging.error(f"❌ process_reason: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка")
        await state.finish()  # ✅ Даже при ошибке сбрасываем состояние

@dp.message_handler(state=ActionState.waiting_proof, content_types=types.ContentTypes.ANY)
async def process_proof(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        idx = data.get("complaint_index")
        if idx is None:
            await state.finish()
            return
        proof = ""
        if message.photo:
            proof = f"📷 Фото: {message.photo[-1].file_id}"
        elif message.document:
            proof = f"📄 Файл: {message.document.file_name}"
        elif message.video:
            proof = f"🎥 Видео: {message.video.file_id}"
        elif message.text:
            proof = f"📝 Текст: {message.text}"
        else:
            proof = "📎 Вложение"
        add_proof_to_complaint(idx, proof)
        admin_id = data.get("admin_id")
        if admin_id:
            try:
                await bot.send_message(admin_id, f"📬 Доказательства по жалобе #{idx}\n{proof}")
            except:
                pass
        await message.answer("✅ Доказательства приняты")
        await state.finish()
    except Exception as e:
        logging.error(f"❌ process_proof: {e}")
# =========================
# вызов в суд
# =========================
@dp.message_handler(state=ActionState.waiting_court_time)
async def process_court_time(message: types.Message, state: FSMContext):
    import re
    time_str = message.text.strip()
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}$', time_str):
        await message.answer("❌ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
        return

    await state.update_data(court_time=time_str)
    await ActionState.waiting_court_reason.set()
    await message.answer("📝 Укажите причину вызова в суд:")
@dp.message_handler(state=ActionState.waiting_court_reason)
async def process_court_reason(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        member = data.get("member")
        time_str = data.get("court_time")
        reason = message.text.strip()
        admin_info = f"{message.from_user.full_name} (@{message.from_user.username or 'admin'})"

        # Получаем TG ID игрока по нику
        info = get_member_info(member)
        tg_id = info.get('tg_id', '').strip() if info else None

        # Ссылка на Discord (берётся из .env)
        discord_link = os.getenv("DISCORD_LINK")

        # 📩 Сообщение для игрока
        player_text = (
            f"🔔 <b>ВЫЗОВ В СУД КЛАНА [PET]</b>\n\n"
            f"👤 Обвиняемый: <code>{member}</code>\n"
            f"⚖️ Причина: {reason}\n"
            f"📅 Дата и время: <code>{time_str}</code>\n"
            f"📍 Место: Discord клана\n\n"
            f"⚠️ Явка обязательна! Игнорирование повлечёт санкции.\n"
            f"🔗 Ссылка: {discord_link}"
        )

        # Отправка игроку
        if tg_id and tg_id.isdigit():
            try:
                await bot.send_message(int(tg_id), player_text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"⚠️ Не удалось отправить вызов {member}: {e}")

        # 🔔 Уведомление всем админам
        admin_notify = f"✅ <b>{member}</b> вызван в суд.\n🕒 {time_str}\n📝 {reason}\n🛡 Инициатор: {admin_info}"
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, admin_notify, parse_mode="HTML")
            except: pass

        # 📝 ЛОГГИРОВАНИЕ В ТАБЛИЦУ "логи"
        append_log("ВЫЗОВ_В_СУД", message.from_user.full_name, message.from_user.id, f"{member} | {time_str}")

        # Возврат в главное меню
        existing_nick = find_member_by_tg_id(message.from_user.id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(message.from_user.id) for app in apps)

        await message.answer(
            f"✅ <b>{member}</b> успешно вызван в суд!\n📅 Время: <code>{time_str}</code>\n📜 Запись добавлена в логи.",
            reply_markup=main_menu(message.from_user.id, is_registered=(existing_nick is not None), has_pending_app=has_pending),
            parse_mode="HTML"
        )
        await state.finish()

    except Exception as e:
        logging.error(f"❌ process_court_reason: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при оформлении вызова.")
        await state.finish()
# =========================
# 🎖 РАЗРЯДЫ
# =========================
@dp.callback_query_handler(lambda c: c.data == "roles_menu")
async def roles_menu(callback: types.CallbackQuery):
    try:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"🪖 Сквадные ({count_by_role('сквадной')})", callback_data="role_сквадной"), InlineKeyboardButton(f"🎯 Пехи ({count_by_role('пех')})", callback_data="role_пех"), InlineKeyboardButton(f"🔧 Техи ({count_by_role('тех')})", callback_data="role_тех"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text("Выбери категорию:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ roles_menu: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("role_"))
async def show_role_members(callback: types.CallbackQuery):
    try:
        role = callback.data.replace("role_", "", 1)
        members = get_members_by_role(role)
        kb = InlineKeyboardMarkup(row_width=2)
        for m in members:
            kb.add(InlineKeyboardButton(m, callback_data=f"editrole_{m[:50]}"))
        kb.add(InlineKeyboardButton("⬅ Назад", callback_data="roles_menu"))
        await callback.message.edit_text(f"{role.upper()} ({len(members)}):", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ show_role_members: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("editrole_"))
async def edit_role(callback: types.CallbackQuery, state: FSMContext):
    try:
        member = callback.data.replace("editrole_", "", 1)
        await state.update_data(role_member=member)
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🪖 Сквадной", callback_data="setrole_сквадной"), InlineKeyboardButton("🎯 Пех", callback_data="setrole_пех"), InlineKeyboardButton("🔧 Тех", callback_data="setrole_тех"), InlineKeyboardButton("⬅ Назад", callback_data="roles_menu"))
        safe_member = html_lib.escape(member)
        await callback.message.edit_text(f"Переназначить роль для {safe_member}:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ edit_role: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("setrole_"))
async def set_new_role(callback: types.CallbackQuery, state: FSMContext):
    try:
        new_role = callback.data.replace("setrole_", "", 1)
        member = (await state.get_data()).get("role_member")
        if member:
            update_role(member, new_role)
            safe_member = html_lib.escape(member)
            user_id = callback.from_user.id
            existing_nick = find_member_by_tg_id(user_id)
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)

            await callback.message.edit_text(f"✅ Роль для {safe_member} обновлена на {new_role}", reply_markup=main_menu(callback.from_user.id, is_registered=(existing_nick is not None),
                                                        has_pending_app=has_pending))
        else:
            await callback.message.edit_text("❌ Ошибка: участник не найден")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ set_new_role: {e}")

# =========================
# 📊 СТАТИСТИКА
# =========================
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    try:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📅 За неделю", callback_data="stats_week"), InlineKeyboardButton("📈 За всё время", callback_data="stats_all"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text("📊 Выберите период:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats: {e}")

@dp.callback_query_handler(lambda c: c.data == "stats_week")
async def stats_week(callback: types.CallbackQuery):
    try:
        top = get_top_praises(weeks=1)
        text = "📭 За неделю похвал ещё нет." if not top else "🏆 ТОП-10 за неделю:\n" + "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="stats"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu")), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats_week: {e}")

@dp.callback_query_handler(lambda c: c.data == "stats_all")
async def stats_all(callback: types.CallbackQuery):
    try:
        top = get_top_praises(weeks=None)
        text = "📭 Похвал ещё нет." if not top else "🏆 ТОП-10 за всё время:\n" + "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="stats"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu")), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats_all: {e}")

#== == == == == == == == == == == == =
#📢 ОПОВЕЩЕНИЯ
#== == == == == == == == == == == == =

class NotifyState(StatesGroup):
    waiting_message = State()
    waiting_audience = State()
    waiting_photo = State()  # Новое состояние для фото


@dp.callback_query_handler(lambda c: c.data == "notify_menu")
async def notify_menu(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("👥 Всем участникам", callback_data="notify_all"),
            InlineKeyboardButton("🎖 Только админам", callback_data="notify_admins"),
            InlineKeyboardButton("🪖 Сквадным", callback_data="notify_role_сквадной"),
            InlineKeyboardButton("🎯 Пехам", callback_data="notify_role_пех"),
            InlineKeyboardButton("🔧 Техам", callback_data="notify_role_тех"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text(
            "📢 Оповещения\nВыберите аудиторию:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ notify_menu: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("notify_"))
async def notify_select_audience(callback: types.CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        audience = callback.data.replace("notify_", "")
        await state.update_data(notify_audience=audience)
        await NotifyState.waiting_message.set()

        audience_names = {
            "all": "всем участникам",
            "admins": "админам",
            "role_сквадной": "сквадным",
            "role_пех": "пехам",
            "role_тех": "техам"
        }

        await callback.message.edit_text(
            f"📢 Оповещение для: {audience_names.get(audience, 'выбранной группы')}\n\n"
            "📝 Введите текст сообщения (или /cancel):",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Отмена", callback_data="back_menu")
            )
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ notify_select_audience: {e}")


@dp.message_handler(state=NotifyState.waiting_message)
async def notify_process_message(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        audience = data.get("notify_audience")
        text = message.text

        await state.update_data(notify_text=text)
        await NotifyState.waiting_photo.set()

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📷 Отправить с фото", callback_data="notify_with_photo"),
            InlineKeyboardButton("⏭ Пропустить (без фото)", callback_data="notify_no_photo")
        )

        await message.answer(
            "📎 Хотите прикрепить фото к оповещению?\n\n"
            "Отправьте фото сейчас или выберите:",
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"❌ notify_process_message: {e}")
@dp.callback_query_handler(lambda c: c.data == "notify_no_photo", state=NotifyState.waiting_photo)
async def notify_no_photo(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(photo_file_id=None)
    await finalize_notification(callback.message, state)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "notify_with_photo", state=NotifyState.waiting_photo)
async def notify_with_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📸 Отправьте фото сейчас (или /cancel):")
    await callback.answer()

@dp.message_handler(state=NotifyState.waiting_photo, content_types=types.ContentTypes.PHOTO)
async def notify_receive_photo(message: types.Message, state: FSMContext):
    try:
        photo_file_id = message.photo[-1].file_id
        await state.update_data(photo_file_id=photo_file_id)
        await finalize_notification(message, state)
    except Exception as e:
        logging.error(f"❌ notify_receive_photo: {e}")
        await message.answer("❌ Ошибка сохранения фото")
        await state.finish()


async def finalize_notification(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        audience = data.get("notify_audience")
        text = data.get("notify_text")
        photo_file_id = data.get("photo_file_id")

        # Получаем список получателей (как в предыдущем коде)
        recipients = get_recipients_by_audience(audience)

        if not recipients:
            await message.answer("❌ Нет получателей")
            await state.finish()
            return

        sent_count = 0
        failed_count = 0

        for user_id in recipients:
            try:
                if photo_file_id:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=photo_file_id,
                        caption=f"📢 <b>Оповещение</b>\n\n{text}",
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"📢 <b>Оповещение</b>\n\n{text}",
                        parse_mode="HTML"
                    )
                sent_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"❌ Ошибка отправки {user_id}: {e}")
                failed_count += 1

        # Отправка в тему группы (если всем)
        if audience == "all" and REPORT_CHAT_ID:
            try:
                if photo_file_id:
                    if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
                        await bot.send_photo(
                            chat_id=REPORT_CHAT_ID,
                            photo=photo_file_id,
                            caption=f"📢 <b>Оповещение для всех</b>\n\n{text}",
                            parse_mode="HTML",
                            message_thread_id=int(WARN_CHAT_ID)
                        )
                    else:
                        await bot.send_photo(
                            chat_id=REPORT_CHAT_ID,
                            photo=photo_file_id,
                            caption=f"📢 <b>Оповещение для всех</b>\n\n{text}",
                            parse_mode="HTML"
                        )
                else:
                    if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
                        await bot.send_message(
                            chat_id=REPORT_CHAT_ID,
                            text=f"📢 <b>Оповещение для всех</b>\n\n{text}",
                            parse_mode="HTML",
                            message_thread_id=int(WARN_CHAT_ID)
                        )
                    else:
                        await bot.send_message(
                            chat_id=REPORT_CHAT_ID,
                            text=f"📢 <b>Оповещение для всех</b>\n\n{text}",
                            parse_mode="HTML"
                        )
            except Exception as e:
                logging.error(f"❌ Ошибка отправки в группу: {e}")

        await message.answer(
            f"✅ Оповещение отправлено!\n\n"
            f"📊 Статистика:\n"
            f"• Отправлено: {sent_count}\n"
            f"• Ошибок: {failed_count}\n"
            f"• С фото: {'✅' if photo_file_id else '❌'}",
            reply_markup=main_menu(message.from_user.id, is_registered=True)
        )

        await state.finish()

    except Exception as e:
        logging.error(f"❌ finalize_notification: {e}")
        await message.answer("❌ Ошибка при отправке")
        await state.finish()


def get_recipients_by_audience(audience):
    """Получить список получателей по аудитории"""
    recipients = []

    if audience == "all":
        ws = sheet.worksheet("участники клана")
        rows = ws.get_all_values()[1:]
        for row in rows:
            if len(row) >= 9 and row[8].strip():
                try:
                    recipients.append(int(row[8]))
                except:
                    pass
        recipients.extend(ADMINS)
        recipients = list(set(recipients))

    elif audience == "admins":
        recipients = ADMINS

    elif audience.startswith("role_"):
        role = audience.replace("role_", "")
        members = get_members_by_role(role)
        ws = sheet.worksheet("участники клана")
        rows = ws.get_all_values()[1:]
        for row in rows:
            if len(row) >= 9 and row[0].strip() in members and row[8].strip():
                try:
                    recipients.append(int(row[8]))
                except:
                    pass

    return recipients
# =========================
# 📄 ШАБЛОНЫ ОТЧЁТОВ
# =========================
@dp.callback_query_handler(lambda c: c.data == "templates_menu")
async def templates_menu(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return
        templates = get_report_templates()
        kb = InlineKeyboardMarkup()
        for t in templates:
            kb.add(InlineKeyboardButton(f"{'✅' if t['active'] else '⭕'} {t['name']}", callback_data=f"tmpl_view_{t['id']}"))
        kb.add(InlineKeyboardButton("➕ Добавить", callback_data="tmpl_add"), InlineKeyboardButton("🔄 Тест", callback_data="tmpl_test"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text("📄 Шаблоны отчётов\nЗелёная галочка = активный", reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ templates_menu: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("tmpl_"))
async def template_actions(callback: types.CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return
        parts = callback.data.split("_")
        action = parts[1] if len(parts) > 1 else ""
        admin = callback.from_user
        admin_name = f"@{admin.username}" if admin.username else admin.full_name
        admin_id = admin.id
        if action == "test":
            await callback.message.answer(f"🧪 Тест:\n{generate_weekly_report()}", parse_mode="HTML")
            await callback.answer("✅ Сгенерирован", show_alert=True)
            return
        if action == "add":
            await state.update_data(template_action="add")
            await ActionState.new_template_name.set()
            await callback.message.answer("📝 Введите название шаблона:")
            return
        if action == "view":
            tid = parts[2] if len(parts) > 2 else None
            tmpl = next((t for t in get_report_templates() if t["id"] == tid), None) if tid else None
            if not tmpl:
                await callback.answer("❌ Не найден", show_alert=True)
                return
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("✏️ Текст", callback_data=f"tmpl_edit_text_{tid}"), InlineKeyboardButton("🔄 Активировать" if not tmpl["active"] else "✅ Активен", callback_data=f"tmpl_activate_{tid}"), InlineKeyboardButton("🗑 Удалить", callback_data=f"tmpl_delete_{tid}"), InlineKeyboardButton("🔙 Назад", callback_data="templates_menu"))
            preview = tmpl["text"][:200] + "..." if len(tmpl["text"]) > 200 else tmpl["text"]
            await callback.message.edit_text(f"📄 {tmpl['name']}\n`{preview}`\n🔁 {'✅ Активен' if tmpl['active'] else '⭕ Не активен'}", reply_markup=kb, parse_mode="HTML")
            return
        if action == "edit" and len(parts) >= 4 and parts[2] == "text":
            tid = parts[3] if len(parts) > 3 else None
            if not tid:
                await callback.answer("❌ Ошибка", show_alert=True)
                return
            await state.update_data(template_action="edit", template_id=tid)
            await ActionState.editing_template.set()
            await callback.message.answer("✏️ Введите новый текст. Переменные: {top_list}, {date}, {week_start}")
            return
        if action == "activate":
            tid = parts[2] if len(parts) > 2 else None
            if not tid:
                await callback.answer("❌ Ошибка", show_alert=True)
                return
            for t in get_report_templates():
                update_template(t["id"], "active", "нет")
            update_template(tid, "active", "да")
            append_log("АКТИВАЦИЯ_ШАБЛОНА", admin_name, admin_id, f"Шаблон ID:{tid}")
            await callback.answer("✅ Активирован!", show_alert=True)
            await templates_menu_show(callback.message)
            return
        if action == "delete":
            tid = parts[2] if len(parts) > 2 else None
            if not tid:
                await callback.answer("❌ Ошибка", show_alert=True)
                return
            ws = get_templates_sheet()
            rows = ws.get_all_values()
            for idx, row in enumerate(rows[1:], start=2):
                if row[0] == tid:
                    ws.delete_rows(idx, idx)
                    break
            append_log("УДАЛЕНИЕ_ШАБЛОНА", admin_name, admin_id, f"Шаблон ID:{tid}")
            await callback.answer("🗑 Удалён", show_alert=True)
            await templates_menu_show(callback.message)
            return
        await callback.answer("❌ Неизвестное", show_alert=True)
    except Exception as e:
        logging.error(f"❌ template_actions: {e}")

async def templates_menu_show(message: types.Message):
    try:
        templates = get_report_templates()
        kb = InlineKeyboardMarkup()
        for t in templates:
            kb.add(InlineKeyboardButton(f"{'✅' if t['active'] else '⭕'} {t['name']}", callback_data=f"tmpl_view_{t['id']}"))
        kb.add(InlineKeyboardButton("➕ Добавить", callback_data="tmpl_add"), InlineKeyboardButton("🔄 Тест", callback_data="tmpl_test"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await message.edit_text("📄 Шаблоны отчётов", reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ templates_menu_show: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("tmpl_edit_text_"))
async def edit_template_text(callback: types.CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return
        tid = callback.data.replace("tmpl_edit_text_", "", 1)
        await state.update_data(template_action="edit", template_id=tid)
        await ActionState.editing_template.set()
        await callback.message.answer("✏️ Введите новый текст. Переменные: {top_list}, {date}, {week_start}")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ edit_template_text: {e}")

@dp.message_handler(state=ActionState.editing_template)
async def save_template_text(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        tid = data.get("template_id")
        if not tid:
            await message.answer("❌ Ошибка")
            await state.finish()
            return
        update_template(tid, "text", message.text)
        user = message.from_user
        username = f"@{user.username}" if user.username else user.full_name
        append_log("ИЗМЕНЕНИЕ_ШАБЛОНА", username, user.id, f"Шаблон ID:{tid}")
        user_id = message.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)
        await message.answer("✅ Обновлено!", reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending))
        await state.finish()
    except Exception as e:
        logging.error(f"❌ save_template_text: {e}")

@dp.message_handler(state=ActionState.new_template_name)
async def save_template_name(message: types.Message, state: FSMContext):
    try:
        await state.update_data(new_template_name=message.text)
        await ActionState.new_template_text.set()
        await message.answer("📝 Теперь введите текст шаблона: Переменные: {top_list}, {date}, {week_start}")
    except Exception as e:
        logging.error(f"❌ save_template_name: {e}")

@dp.message_handler(state=ActionState.new_template_text)
async def save_new_template(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        name, text = data.get("new_template_name"), message.text
        if not name or not text:
            await message.answer("❌ Ошибка")
            await state.finish()
            return
        new_id = add_template(name, text)
        user = message.from_user
        username = f"@{user.username}" if user.username else user.full_name
        append_log("СОЗДАНИЕ_ШАБЛОНА", username, user.id, f"Шаблон '{name}' ID:{new_id}")
        user_id = message.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)
        await message.answer(f"✅ Создан! ID: {new_id}", reply_markup=main_menu(user_id, is_registered=(existing_nick is not None), has_pending_app=has_pending))
        await state.finish()
    except Exception as e:
        logging.error(f"❌ save_new_template: {e}")

# =========================
# 📝 ЛОГИ
# =========================
@dp.callback_query_handler(lambda c: c.data == "logs")
async def logs(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Доступ только для админов", show_alert=True)
            return

        logs_data = get_logs()[-10:]

        if len(logs_data) <= 1:
            text = "📭 Логи пусты"
        else:
            text = "🕒 Последние 10 действий:\n"
            for row in logs_data[-1:0:-1]:
                if len(row) >= 5:
                    # ✅ Используем HTML-экранирование вместо Markdown
                    action = html_lib.escape(row[0])
                    username = html_lib.escape(row[1])
                    target = html_lib.escape(row[3])
                    date = html_lib.escape(row[4])
                    text += f"<code>{date}</code> | {action} | {username} → {target}\n"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs"))
        keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

        # ✅ Используем parse_mode="HTML" вместо Markdown
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ logs: {e}")
        await callback.answer("❌ Ошибка загрузки логов", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "clear_logs")
async def clear_logs_handler(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return
        clear_logs()
        await callback.message.edit_text("✅ Очищено", reply_markup=main_menu(callback.from_user.id))
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ clear_logs: {e}")

# =========================
# ⚖ ЖАЛОБЫ
# =========================
@dp.callback_query_handler(lambda c: c.data == "complaints")
async def complaints_menu(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return
        rows = get_complaints()
        kb = InlineKeyboardMarkup()
        active = [r for r in rows[1:] if len(r) >= 6 and r[5] == "активна"]
        if not active:
            kb.add(InlineKeyboardButton("📭 Нет жалоб", callback_data="none"))
        else:
            for i, r in enumerate(active):
                kb.add(InlineKeyboardButton(f"🔴 {r[2] if len(r) > 2 else '?'}", callback_data=f"complaint_{rows.index(r)-1}"))
        kb.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text("⚖ Активные жалобы:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ complaints_menu: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_"))
async def complaint_actions(callback: types.CallbackQuery):
    try:
        data = callback.data.split("_")
        admin_info = f"{callback.from_user.full_name} @{callback.from_user.username}".strip()
        if data[1] == "pred" and len(data) >= 3:
            try:
                idx = int(data[2])
            except:
                return await callback.answer("❌ Ошибка", show_alert=True)
            rows = get_complaints()
            if idx + 1 >= len(rows):
                return await callback.answer("❌ Не найдено", show_alert=True)
            row = rows[idx + 1]
            violator, reason, sender_id = (row[2] if len(row) > 2 else "?"), (row[3] if len(row) > 3 else "?"), (row[1] if len(row) > 1 else None)
            append_pred(violator, f"По жалобе: {reason}")
            append_log(f"ПРЕД_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, violator)
            close_complaint(idx, closed_by=admin_info)
            if sender_id:
                try:
                    await bot.send_message(int(sender_id), f"✅ Жалоба на {violator} рассмотрена. Выдан ПРЕД.", parse_mode="HTML")
                except:
                    pass
            user_id = callback.from_user.id
            existing_nick = find_member_by_tg_id(user_id)
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)
            await callback.message.edit_text(f"⚠ ПРЕД выдан {violator}. Жалоба закрыта ✅", reply_markup=main_menu(callback.from_user.id, is_registered=(existing_nick is not None),
                                                        has_pending_app=has_pending))
            return
        if data[1] == "request" and data[2] == "proof" and len(data) >= 4:
            try:
                idx = int(data[3])
            except:
                return await callback.answer("❌ Ошибка", show_alert=True)
            rows = get_complaints()
            if idx + 1 >= len(rows):
                return await callback.answer("❌ Не найдено", show_alert=True)
            row = rows[idx + 1]
            sender_id, target = (row[1] if len(row) > 1 else None), (row[2] if len(row) > 2 else "?")
            append_log(f"ЗАПРОС_ДОКОВ_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, target)
            if sender_id:
                try:
                    await dp.storage.set_state(chat=int(sender_id), user=int(sender_id), state=ActionState.waiting_proof)
                    await dp.storage.set_data(chat=int(sender_id), user=int(sender_id), data={"complaint_index": idx, "admin_id": callback.from_user.id})
                    await bot.send_message(int(sender_id), f"🔍 Запрошены доказательства по жалобе на {target}.", parse_mode="HTML")
                    await callback.answer("📩 Запрос отправлен", show_alert=True)
                except Exception as e:
                    await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
            else:
                await callback.answer("❌ Не найден ID", show_alert=True)
            return
        if data[1] == "close" and data[2] == "noaction" and len(data) >= 4:
            try:
                idx = int(data[3])
            except:
                return await callback.answer("❌ Ошибка", show_alert=True)
            rows = get_complaints()
            if idx + 1 >= len(rows):
                return await callback.answer("❌ Не найдено", show_alert=True)
            row = rows[idx + 1]
            sender_id, target = (row[1] if len(row) > 1 else None), (row[2] if len(row) > 2 else "?")
            append_log(f"ЖАЛОБА_ЗАКРЫТА_БЕЗ_ДЕЙСТВИЙ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, target)
            close_complaint(idx, closed_by=admin_info)
            if sender_id:
                try:
                    await bot.send_message(int(sender_id), f"ℹ️ Жалоба на {target} закрыта без санкций.", parse_mode="HTML")
                except:
                    pass
            user_id = callback.from_user.id
            existing_nick = find_member_by_tg_id(user_id)
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)
            await callback.message.edit_text("✅ Жалоба закрыта", reply_markup=main_menu(callback.from_user.id,is_registered=(existing_nick is not None),
                                                        has_pending_app=has_pending))
            return
        try:
            idx = int(data[1])
        except:
            return await callback.answer("❌", show_alert=True)
        rows = get_complaints()
        if idx + 1 >= len(rows):
            return await callback.answer("❌ Не найдено", show_alert=True)
        row = rows[idx + 1]
        text = f"⚖ ЖАЛОБА #{idx}\n👤 От: {row[0] if len(row) > 0 else '?'}\n🎯 На: {row[2] if len(row) > 2 else '?'}\n📝 Причина: {row[3] if len(row) > 3 else '?'}\n🕒 Дата: {row[4] if len(row) > 4 else '?'}\n📎 Доки: {row[6] if len(row) > 6 and row[6] else 'Нет'}\n🔖 Статус: {row[5] if len(row) > 5 else '?'}"
        if len(row) > 7 and row[7]:
            text += f"\n🔒 Закрыл: {row[7]}"
        kb = InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("⚠ ПРЕД + закрыть", callback_data=f"complaint_pred_{idx}"), InlineKeyboardButton("📸 Запросить доки", callback_data=f"complaint_request_proof_{idx}"), InlineKeyboardButton("❌ Закрыть (ничего)", callback_data=f"complaint_close_noaction_{idx}"), InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ complaint_actions: {e}")



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
# 🔤 АВТО-ОТВЕТЫ НА СЛОВА
# =========================

# # Слова для отслеживания
# JDM_TRIGGERS = ["jdm", "ждм", "JDM", "ЖДМ", "Jdm", "Ждм"]
# YATO_TRIGGERS = ["ЯТО","ято","Ято","Yatoo","YATOO"]
# PRO_TRIGGERS = ["ПРОТОКОЛ","протокол","PROTOCOL","protocol","Протокол"]
# # Ответ бота (можно менять)
# JDM_RESPONSE = """
# <b>JDM лохи!!! слава петушкам!!!</b>
# """
# YATO_RESPONSE = """
# <b>ЯТО ХУЕСОС, ПОЗОР ЕМУ!!!</b>
# """
# PRO_RESPONSE = """ <b> Нахуй этот пивной гнилой сервак . Идите на мжд!!! </b> """
# @dp.message_handler()
# async def auto_response_jdm(message: types.Message):
#     """Отвечает на слова jdm/ждм в чате"""
#     try:
#         # Не отвечаем ботам и в личных сообщениях
#         if message.from_user.is_bot:
#             return
#
#         # Проверяем, что это группа (не ЛС)
#         if message.chat.type == "private":
#             return
#
#         # Получаем текст сообщения
#         text = message.text
#         if not text:
#             return
#
#         # Проверяем наличие триггеров (без учёта регистра)
#         text_lower = text.lower()
#         if any(trigger.lower() in text_lower for trigger in JDM_TRIGGERS):
#             # Отвечаем с задержкой 1 секунда (чтобы выглядело естественнее)
#             await asyncio.sleep(1)
#             await message.answer(JDM_RESPONSE, parse_mode="HTML")
#             logging.info(f"🏎️ JDM-ответ отправлен в чате {message.chat.id}")
#         if any(trigger.lower() in text_lower for trigger in YATO_TRIGGERS):
#             # Отвечаем с задержкой 1 секунда (чтобы выглядело естественнее)
#             await asyncio.sleep(1)
#             await message.answer(YATO_RESPONSE, parse_mode="HTML")
#             logging.info(f"🏎️ YATO-ответ отправлен в чате {message.chat.id}")
#         if any(trigger.lower() in text_lower for trigger in PRO_TRIGGERS):
#             # Отвечаем с задержкой 1 секунда (чтобы выглядело естественнее)
#             await asyncio.sleep(1)
#             await message.answer(PRO_RESPONSE, parse_mode="HTML")
#             logging.info(f"🏎️ PRO-ответ отправлен в чате {message.chat.id}")
#     except Exception as e:
#         logging.error(f"❌ auto_response_jdm: {e}")
#
#
# # =========================
# # 🎛 АДМИН-КОМАНДЫ ДЛЯ JDM
# # =========================
#
# @dp.message_handler(commands=["set_jdm_response"])
# async def set_jdm_response(message: types.Message):
#     """Админ меняет текст ответа на jdm"""
#     if message.from_user.id not in ADMINS:
#         await message.answer("❌ Только для админов")
#         return
#
#     new_text = message.text.replace("/set_jdm_response", "").strip()
#     if not new_text:
#         await message.answer(
#             "❌ Введите текст после команды\n\n"
#             "Пример:\n"
#             "/set_jdm_response 🏎️ JDM FOREVER!"
#         )
#         return
#
#     global JDM_RESPONSE
#     JDM_RESPONSE = new_text
#     await message.answer("✅ Текст ответа на JDM обновлён!")
#     logging.info(f"📝 JDM-ответ изменён админом {message.from_user.full_name}")


#== == == == == == == == == == == == =
#🎫 ТИКЕТЫ
#ЧЕРЕЗ
#ГРУППУ
#МОДЕРАТОРОВ
#== == == == == == == == == == == == =

MODS_CHAT_ID = int(os.getenv("MODS_CHAT_ID"))
@dp.callback_query_handler(lambda c: c.data == "ticket_create")
async def ticket_create(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await callback.answer("⚠️ Завершите текущее действие сначала", show_alert=True)
        return

    await TicketState.waiting_user_msg.set()
    await callback.message.edit_text(
        "✉️ <b>Написать администрации</b>\n\n"
        "Введите ваше обращение или вопрос.\n"
        "Сообщение будет отправлено в группу модераторов.\n\n"
        "🔙 /cancel для отмены",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "ticket_create")
async def ticket_create(callback: types.CallbackQuery, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state is not None:
            await callback.answer("⚠️ Завершите текущее действие сначала", show_alert=True)
            return

        await TicketState.waiting_user_msg.set()
        text = (
            "✉️ <b>Написать администрации</b>\n\n"
            "Введите ваше обращение или вопрос.\n"
            "Сообщение будет отправлено модераторам.\n\n"
            "🔙 /cancel для отмены"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML")
        except:
            await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ ticket_create: {e}")
        await callback.answer("❌ Ошибка открытия формы", show_alert=True)


@dp.message_handler(state=TicketState.waiting_user_msg)
async def process_ticket_message(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        ticket_text = message.text.strip()

        if len(ticket_text) < 3:
            await message.answer("❌ Сообщение слишком короткое. Опишите вопрос подробнее.")
            return

        mod_text = (
            f"🎫 <b>Новый запрос</b>\n"
            f"👤 От: {username}\n"
            f"🆔 ID: <code>{user_id}</code>\n\n"
            f"📝 {html_lib.escape(ticket_text)}"
        )

        # Отправляем в группу модеров или админам в ЛС
        if MODS_CHAT_ID and MODS_CHAT_ID != 0:
            await bot.send_message(MODS_CHAT_ID, mod_text, parse_mode="HTML")
        else:
            for admin_id in ADMINS:
                await bot.send_message(admin_id, mod_text, parse_mode="HTML")

        append_log("ТИКЕТ_СОЗДАН", username, user_id, ticket_text[:50])
        await message.answer("✅ Ваше обращение отправлено!\nОжидайте ответа в ЛС.")
        await state.finish()
    except Exception as e:
        logging.error(f"❌ process_ticket_message: {e}")
        await message.answer("❌ Произошла ошибка при отправке.")


@dp.message_handler(
    lambda msg: msg.chat.id == MODS_CHAT_ID and msg.reply_to_message is not None and "🆔 ID:" in (
            msg.reply_to_message.text or "")
)
async def handle_mod_reply(message: types.Message):
    try:
        reply_text = message.reply_to_message.text
        import re
        match = re.search(r"🆔 ID: <code>(\d+)</code>", reply_text)
        if not match:
            return

        target_user_id = int(match.group(1))
        mod_nick = html_lib.escape(message.from_user.full_name)
        answer_text = html_lib.escape(message.text)

        user_reply = f"🛡 <b>Модератор {mod_nick} ответил на ваш запрос:</b>\n\n{answer_text}"

        try:
            await bot.send_message(target_user_id, user_reply, parse_mode="HTML")
            await message.answer("✅ Ответ доставлен участнику!")
        except Exception as e:
            await message.answer(f"❌ Не удалось доставить ответ. Пользователь заблокировал бота или удалил чат.")

        append_log("ТИКЕТ_ОТВЕТ", message.from_user.full_name, message.from_user.id, f"ID: {target_user_id}")
    except Exception as e:
        logging.error(f"❌ handle_mod_reply: {e}")

async def scheduled_report_job():
    """Еженедельный отчёт"""
    try:
        logging.info("⏰ Запуск задачи: отправка отчёта")
        await send_weekly_report()
    except Exception as e:
        logging.error(f"❌ scheduled_report_job: {e}")


async def check_new_devlogs():
    """Проверяет Google Sheets на новые девлоги"""
    try:
        ws = sheet.worksheet("devlogs")
        rows = ws.get_all_values()[1:]

        devlog_topic = os.getenv("DEVLOGS_TOPIC_ID")
        report_chat = os.getenv("REPORT_CHAT_ID")

        if not report_chat:
            return

        chat_id = int(report_chat)
        topic_id = int(devlog_topic) if devlog_topic and devlog_topic.isdigit() else None

        for idx, row in enumerate(rows, start=2):
            if len(row) < 8:
                continue
            sent_flag = row[7].strip().lower()
            if sent_flag == "yes":
                continue

            author = row[1]
            title = row[2]
            content = row[3]
            photo_url = row[6] if len(row) > 6 else None

            import html
            text = f"📝 <b>Devlog: {html.escape(title)}</b>\n\n"
            text += f"👤 <i>{html.escape(author)}</i>\n\n"
            text += html.escape(content)

            try:
                if photo_url and photo_url.strip():
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_url,
                        caption=text,
                        parse_mode="HTML",
                        message_thread_id=topic_id
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                        message_thread_id=topic_id
                    )
                ws.update_cell(idx, 8, "yes")
                logging.info(f"✅ Девлог #{idx - 1} отправлен")
            except Exception as e:
                logging.error(f"❌ Не отправлен девлог #{idx - 1}: {e}")
    except Exception as e:
        logging.error(f"❌ check_new_devlogs: {e}")


async def process_scheduled_notifications():
    """Проверка запланированных оповещений"""
    try:
        # Ваш код проверки оповещений...
        # (оставьте как есть, если используете)
        pass
    except Exception as e:
        logging.error(f"❌ process_scheduled_notifications: {e}")


async def on_startup(_):
    """Запускается при старте бота — ЕДИНАЯ ФУНКЦИЯ"""
    global scheduler

    logging.info("✅ Бот запущен, инициализация планировщика...")

    # Создаём планировщик с привязкой к текущему event loop
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"), event_loop=asyncio.get_running_loop())

    if REPORT_CHAT_ID:
        # Еженедельный отчёт: суббота 18:30 МСК
        scheduler.add_job(
            scheduled_report_job,
            trigger=CronTrigger(hour=18, minute=30, day_of_week="sat", timezone=pytz.timezone("Europe/Moscow")),
            id="weekly_report",
            replace_existing=True,
            misfire_grace_time=3600  # 1 час на пропущенный запуск
        )
        logging.info("⏰ Задача 'weekly_report' добавлена")

        # Проверка девлогов: каждые 30 секунд
        scheduler.add_job(
            check_new_devlogs,
            trigger=CronTrigger(second="*/30", timezone=pytz.timezone("Europe/Moscow")),
            id="check_devlogs",
            replace_existing=True
        )
        logging.info("⏰ Задача 'check_devlogs' добавлена")

        # Проверка оповещений: каждые 2 минуты
        scheduler.add_job(
            process_scheduled_notifications,
            trigger=CronTrigger(minute="*/2", timezone=pytz.timezone("Europe/Moscow")),
            id="check_notifications",
            replace_existing=True
        )
        logging.info("⏰ Задача 'check_notifications' добавлена")

    # 🚀 Запускаем планировщик
    scheduler.start()
    logging.info("⏰ APScheduler запущен ✅")


async def on_shutdown(_):
    """Корректная остановка"""
    logging.info("🛑 Остановка бота...")

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logging.info("⏰ Планировщик остановлен")

    await bot.close()
    logging.info("🔌 Бот закрыт")
# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)