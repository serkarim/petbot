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

# ---------- Клан ----------
def get_clan_members():
    ws = sheet.worksheet("участники клана")
    return [v for v in ws.col_values(1) if v.strip()]

# ---------- Похвала ----------
def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, from_user, reason, date])

# ---------- Разряды ----------
def get_roles_sheet():
    return sheet.worksheet("разряды")

def get_roles_data():
    ws = get_roles_sheet()
    rows = ws.get_all_values()
    return rows[1:] if len(rows) > 1 else []

def get_members_by_role(role):
    return [r[0] for r in get_roles_data() if len(r) > 1 and r[1].lower() == role]

def count_by_role(role):
    return len(get_members_by_role(role))

def update_role(member, new_role):
    ws = get_roles_sheet()
    rows = ws.get_all_values()

    for idx, row in enumerate(rows):
        if row and row[0] == member:
            ws.update_cell(idx + 1, 2, new_role)
            break

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

class AdminState(StatesGroup):
    waiting_reason = State()

# =========================
# MENU
# =========================

def main_menu(user_id):
    keyboard = InlineKeyboardMarkup()

    if is_admin(user_id):
        keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
        keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
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
        "Главное меню:",
        reply_markup=main_menu(message.from_user.id)
    )

# =========================
# 📋 СПИСОК КЛАНА
# =========================

@dp.callback_query_handler(lambda c: c.data == "clan_list")
async def clan_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    members = get_clan_members()

    if not members:
        await callback.message.answer("Список клана пуст.")
        return

    text = "📋 Участники клана:\n\n"
    for m in members:
        text += f"• {m}\n"

    await callback.message.answer(text)

# =========================
# 👏 Похвала (участники)
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
# 🧾 ЛОГИ
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

    if not rows:
        await callback.message.answer("Логи пустые.")
        return

    text = "\n".join([f"{r[1]} → {r[0]} ({r[2]})" for r in rows[-10:]])
    await callback.message.answer(text)

@dp.callback_query_handler(lambda c: c.data == "clear_logs")
async def clear_logs(callback: types.CallbackQuery):
    ws = sheet.worksheet("Похвала")
    ws.clear()
    ws.append_row(["Ник", "Кто выдал", "Причина", "Дата"])
    await callback.message.answer("🗑 Логи очищены")

# =========================
# 📊 СТАТИСТИКА (СТРОГО 7 ДНЕЙ)
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ws = sheet.worksheet("Похвала")
    rows = ws.get_all_values()

    if len(rows) <= 1:
        await callback.message.answer("Нет данных.")
        return

    rows = rows[1:]

    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

    weekly = []

    for row in rows:
        if len(row) < 4:
            continue

        try:
            date_obj = datetime.strptime(row[3], "%d.%m.%Y").date()
        except:
            continue

        if week_ago <= date_obj <= today:
            weekly.append(row[0])

    if not weekly:
        await callback.message.answer("За последние 7 дней похвал нет.")
        return

    counter = Counter(weekly)
    top5 = counter.most_common(5)

    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
    text = "🏆 ТОП 5 за последние 7 дней:\n\n"

    for i, (nick, count) in enumerate(top5):
        text += f"{medals[i]} {nick} — {count}\n"

    await callback.message.answer(text)

# =========================
# 🎖 РАЗРЯДЫ
# =========================

@dp.callback_query_handler(lambda c: c.data == "roles_menu")
async def roles_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

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

@dp.callback_query_handler(lambda c: c.data.startswith("role_"))
async def show_role_members(callback: types.CallbackQuery):
    role = callback.data.replace("role_", "")
    members = get_members_by_role(role)

    keyboard = InlineKeyboardMarkup(row_width=2)
    for m in members:
        keyboard.insert(InlineKeyboardButton(m, callback_data=f"editrole_{m}"))

    keyboard.add(InlineKeyboardButton("⬅ Назад", callback_data="roles_menu"))

    await callback.message.edit_text(
        f"{role.upper()} ({len(members)}):",
        reply_markup=keyboard
    )

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

    await callback.message.edit_text(
        f"Переназначить роль для {member}:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith("setrole_"))
async def set_new_role(callback: types.CallbackQuery, state: FSMContext):
    new_role = callback.data.replace("setrole_", "")
    data = await state.get_data()
    member = data.get("role_member")

    update_role(member, new_role)

    await callback.message.edit_text(
        f"Роль для {member} обновлена на {new_role}",
        reply_markup=main_menu(callback.from_user.id)
    )

# =========================
# Назад
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