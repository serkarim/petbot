import logging
from datetime import datetime, timedelta
import os
import json

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# 🔐 ENV
# =========================

TOKEN = os.getenv("TOKEN")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))

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
        if row[0] == member:
            ws.update_cell(idx + 1, 2, new_role)
            break

# ---------- СТАТИСТИКА ----------
def get_top_week():
    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()[1:]
    week_ago = datetime.now() - timedelta(days=7)

    counter = {}

    for row in rows:
        try:
            date = datetime.strptime(row[3], "%d.%m.%Y")
            if date >= week_ago:
                member = row[0]
                counter[member] = counter.get(member, 0) + 1
        except:
            continue

    return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]

# ---------- ЖАЛОБЫ ----------
def add_complaint(from_user, against, reason):
    ws = sheet.worksheet("жалобы")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([from_user, against, reason, date, "АКТИВНА"])

def get_active_complaints():
    ws = sheet.worksheet("жалобы")
    rows = ws.get_all_values()
    return [r for r in rows[1:] if len(r) >= 5 and r[4] == "АКТИВНА"]

def close_complaint(index):
    ws = sheet.worksheet("жалобы")
    ws.update_cell(index + 2, 5, "ЗАКРЫТА")

# =========================
# 🤖 INIT
# =========================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# =========================
# MENU
# =========================

def main_menu(user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
    keyboard.add(InlineKeyboardButton("📊 Статистика", callback_data="stats"))
    keyboard.add(InlineKeyboardButton("⚖ Жалобы", callback_data="complaints"))

    if user_id in ADMINS:
        keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
        keyboard.add(InlineKeyboardButton("📝 Логи", callback_data="logs"))

    return keyboard

# =========================
# FSM
# =========================

class ActionState(StatesGroup):
    waiting_reason = State()
    waiting_complaint = State()

# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu(message.from_user.id))

@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu(callback.from_user.id)
    )

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

    await callback.message.edit_text("Выбери участника:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("member_"))
async def member_selected(callback: types.CallbackQuery, state: FSMContext):
    member = callback.data.replace("member_", "")
    await state.update_data(member=member)

    keyboard = InlineKeyboardMarkup()

    if callback.from_user.id in ADMINS:
        keyboard.add(InlineKeyboardButton("⚠ Пред", callback_data="action_pred"))

    keyboard.add(InlineKeyboardButton("👏 Похвала", callback_data="action_praise"))
    keyboard.add(InlineKeyboardButton("⚖ Жалоба", callback_data="action_complaint"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(
        f"Выбран: {member}\n\nВыбери действие:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith("action_"))
async def action_selected(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.replace("action_", "")
    await state.update_data(action=action)
    await ActionState.waiting_reason.set()
    await callback.message.answer("Напиши причину (или /cancel):")

# =========================
# ❌ Отмена
# =========================

@dp.message_handler(commands=["cancel"], state="*")
async def cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Отменено", reply_markup=main_menu(message.from_user.id))

# =========================
# ✍ Запись (пред / похвала / жалоба)
# =========================

@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    member = data["member"]
    action = data["action"]

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    user_id = user.id

    if action == "pred":
        if user_id not in ADMINS:
            await message.answer("Нет прав ❌")
            await state.finish()
            return

        append_pred(member, message.text)
        append_log("ПРЕД", username, user_id, member)
        await message.answer("⚠ Пред записан")

    elif action == "praise":
        append_praise(member, username, message.text)
        append_log("ПОХВАЛА", username, user_id, member)
        await message.answer("👏 Похвала записана")

    elif action == "complaint":
        add_complaint(username, member, message.text)
        await message.answer("⚖ Жалоба отправлена")

    await state.finish()
    await message.answer("Главное меню:", reply_markup=main_menu(user_id))

# =========================
# 🎖 РАЗРЯДЫ
# =========================

@dp.callback_query_handler(lambda c: c.data == "roles_menu")
async def roles_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(
        f"🪖 Сквадные ({count_by_role('сквадной')})",
        callback_data="role_сквадной"
    ))
    keyboard.add(InlineKeyboardButton(
        f"🎯 Пехи ({count_by_role('пех')})",
        callback_data="role_пех"
    ))
    keyboard.add(InlineKeyboardButton(
        f"🔧 Техи ({count_by_role('тех')})",
        callback_data="role_тех"
    ))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text("Выбери категорию:", reply_markup=keyboard)

# =========================
# 📊 СТАТИСТИКА
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    top = get_top_week()

    text = "🏆 ТОП 5 за неделю:\n\n"
    if not top:
        text = "За 7 дней похвалы нет."
    else:
        for i, (member, count) in enumerate(top, 1):
            text += f"{i}. {member} — {count}\n"

    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))

# =========================
# ⚖ ЖАЛОБЫ
# =========================

@dp.callback_query_handler(lambda c: c.data == "complaints")
async def complaints_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📩 Подать жалобу", callback_data="new_complaint"))

    if callback.from_user.id in ADMINS:
        keyboard.add(InlineKeyboardButton("📜 Жалобы (админ)", callback_data="list_complaints"))

    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text("⚖ Жалобы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "new_complaint")
async def new_complaint(callback: types.CallbackQuery):
    members = get_clan_members()
    keyboard = InlineKeyboardMarkup(row_width=2)

    for m in members:
        keyboard.insert(InlineKeyboardButton(m, callback_data=f"complaint_to_{m}"))

    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text("На кого жалоба?", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_to_"))
async def complaint_reason(callback: types.CallbackQuery, state: FSMContext):
    member = callback.data.replace("complaint_to_", "")
    await state.update_data(complaint_to=member)
    await ActionState.waiting_complaint.set()
    await callback.message.answer("Напиши причину жалобы:")

@dp.message_handler(state=ActionState.waiting_complaint)
async def process_complaint(message: types.Message, state: FSMContext):
    data = await state.get_data()
    to = data["complaint_to"]
    from_user = message.from_user.username or message.from_user.full_name

    add_complaint(from_user, to, message.text)
    await message.answer("⚖ Жалоба отправлена", reply_markup=main_menu(message.from_user.id))
    await state.finish()

# =========================
# АДМИН: СПИСОК ЖАЛОБ
# =========================

@dp.callback_query_handler(lambda c: c.data == "list_complaints")
async def list_complaints(callback: types.CallbackQuery):
    complaints = get_active_complaints()

    if not complaints:
        await callback.message.edit_text("Активных жалоб нет.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for i, row in enumerate(complaints):
        sender, against, reason, date, _ = row
        keyboard.add(InlineKeyboardButton(
            f"{against} — {reason} ({date})",
            callback_data=f"complaint_{i}"
        ))

    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text("Активные жалобы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_"))
async def complaint_actions(callback: types.CallbackQuery):
    index = int(callback.data.split("_")[1])

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("⚠ Выдать пред", callback_data=f"complaint_warn_{index}"))
    keyboard.add(InlineKeyboardButton("📎 Запросить доказательства", callback_data=f"complaint_evidence_{index}"))
    keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data=f"complaint_close_{index}"))

    await callback.message.edit_text("Действия:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_warn_"))
async def complaint_warn(callback: types.CallbackQuery):
    index = int(callback.data.split("_")[2])
    complaints = get_active_complaints()
    row = complaints[index]

    sender, against, reason, _, _ = row
    append_pred(against, f"Жалоба от {sender}: {reason}")
    close_complaint(index)

    await callback.message.edit_text("Пред выдан и жалоба закрыта.")

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_evidence_"))
async def complaint_evidence(callback: types.CallbackQuery):
    await callback.message.answer("Пришлите доказательства — они будут прикреплены к жалобе.")

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_close_"))
async def complaint_close(callback: types.CallbackQuery):
    index = int(callback.data.split("_")[2])
    close_complaint(index)
    await callback.message.edit_text("Жалоба закрыта.")

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)