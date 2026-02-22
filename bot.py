import logging
from datetime import datetime, timedelta
import os
import json
from collections import Counter

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
MY_NAME = os.getenv("MY_NAME")

ADMINS = os.getenv("ADMINS", "")
ADMINS = [int(x) for x in ADMINS.split(",") if x.strip()]

def is_admin(user_id):
    return user_id in ADMINS

# =========================
# 📊 Google Sheets
# =========================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_env = os.getenv("CREDS_JSON")
if not creds_env:
    raise Exception("CREDS_JSON не задан")

creds_data = json.loads(creds_env)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_KEY)

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
    ws.append_row([member, from_user, reason, date])

# =========================
# 🤖 INIT
# =========================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# =========================
# FSM
# =========================

class PraiseState(StatesGroup):
    waiting_nick = State()
    waiting_reason = State()

class AdminActionState(StatesGroup):
    waiting_reason = State()

# =========================
# MENU
# =========================

def main_menu(user_id):
    keyboard = InlineKeyboardMarkup()

    if is_admin(user_id):
        keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
        keyboard.add(InlineKeyboardButton("📊 Статистика", callback_data="stats"))
        keyboard.add(InlineKeyboardButton("🧾 Логи", callback_data="logs_menu"))
    else:
        keyboard.add(InlineKeyboardButton("👏 Выдать похвалу", callback_data="give_praise"))

    return keyboard

# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        f"Твой Telegram ID: {message.from_user.id}",
        reply_markup=main_menu(message.from_user.id)
    )

# =========================
# 👏 Участники — похвала
# =========================

@dp.callback_query_handler(lambda c: c.data == "give_praise")
async def give_praise_start(callback: types.CallbackQuery):
    await PraiseState.waiting_nick.set()
    await callback.message.answer("Введите ник участника:")

@dp.message_handler(state=PraiseState.waiting_nick)
async def praise_nick(message: types.Message, state: FSMContext):
    await state.update_data(nick=message.text.strip())
    await PraiseState.waiting_reason.set()
    await message.answer("Введите причину похвалы:")

@dp.message_handler(state=PraiseState.waiting_reason)
async def praise_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    nick = data["nick"]

    from_user = message.from_user
    username = f"@{from_user.username}" if from_user.username else from_user.full_name

    if username.lower() == nick.lower():
        await message.answer("🚫 Нельзя хвалить самого себя.")
        await state.finish()
        return

    append_praise(nick, username, message.text)

    await message.answer("👏 Похвала записана!", reply_markup=main_menu(message.from_user.id))
    await state.finish()

# =========================
# 🧾 ЛОГИ (только админы)
# =========================

@dp.callback_query_handler(lambda c: c.data == "logs_menu")
async def logs_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📄 Показать логи", callback_data="show_logs"))
    keyboard.add(InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text("Логи похвалы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "show_logs")
async def show_logs(callback: types.CallbackQuery):
    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()[1:]

    text = "\n".join([f"{r[1]} → {r[0]} ({r[2]})" for r in rows[-10:]])

    if not text:
        text = "Логи пустые."

    await callback.message.answer(text)

@dp.callback_query_handler(lambda c: c.data == "clear_logs")
async def clear_logs(callback: types.CallbackQuery):
    ws = sheet.worksheet("Похвала")
    ws.clear()
    ws.append_row(["Ник", "Кто выдал", "Причина", "Дата"])
    await callback.message.answer("🗑 Логи очищены")

# =========================
# 📊 ТОП 5 ЗА НЕДЕЛЮ
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()[1:]

    today = datetime.now()
    week_ago = today - timedelta(days=7)

    weekly = []

    for r in rows:
        try:
            date_obj = datetime.strptime(r[3], "%d.%m.%Y")
            if date_obj >= week_ago:
                weekly.append(r[0])
        except:
            continue

    counter = Counter(weekly)
    top5 = counter.most_common(5)

    if not top5:
        await callback.message.answer("Нет похвал за неделю.")
        return

    text = "🏆 ТОП 5 за неделю:\n\n"
    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]

    for i, (nick, count) in enumerate(top5):
        text += f"{medals[i]} {nick} — {count}\n"

    await callback.message.answer(text)

# =========================
# 🔙 Назад
# =========================

@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu(callback.from_user.id)
    )

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)