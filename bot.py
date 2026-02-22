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

def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, reason, date])

def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    date = datetime.now().strftime("%d.%m.%Y")
    # Новый порядок
    ws.append_row([member, from_user, reason, date])

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

# ---------- СТАТИСТИКА ----------

def get_top_week():
    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()[1:]
    week_ago = datetime.now() - timedelta(days=7)

    counter = {}

    for row in rows:
        try:
            date = datetime.strptime(row[3], "%d.%m.%Y")  # теперь 4 столбец
            if date >= week_ago:
                member = row[0]
                counter[member] = counter.get(member, 0) + 1
        except:
            continue

    sorted_data = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    return sorted_data[:5]

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

    if user_id in ADMINS:
        keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
        keyboard.add(InlineKeyboardButton("📝 Логи", callback_data="logs"))

    return keyboard

# =========================
# FSM
# =========================

class ActionState(StatesGroup):
    waiting_reason = State()

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

@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    member = data["member"]
    action = data["action"]
    reason = message.text

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    user_id = user.id

    if action == "pred":
        if user_id not in ADMINS:
            await message.answer("У тебя нет прав ❌")
            await state.finish()
            return

        append_pred(member, reason)
        append_log("ПРЕД", username, user_id, member)
        await message.answer("⚠ Пред записан")
    else:
        append_praise(member, username, reason)
        append_log("ПОХВАЛА", username, user_id, member)
        await message.answer("👏 Похвала записана")

    await state.finish()
    await message.answer("Главное меню:", reply_markup=main_menu(user_id))

# =========================
# 📊 СТАТИСТИКА
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    top = get_top_week()

    if not top:
        text = "За 7 дней похвалы нет."
    else:
        text = "🏆 ТОП 5 за неделю:\n\n"
        for i, (member, count) in enumerate(top, 1):
            text += f"{i}. {member} — {count}\n"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard)

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)