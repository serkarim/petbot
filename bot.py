import logging
from datetime import datetime
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
MY_NAME = os.getenv("MY_NAME")

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

# ---------- Пред ----------
def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, reason, date])

# ---------- Похвала ----------
def append_praise(member, reason):
    ws = sheet.worksheet("Похвала")
    date = datetime.now().strftime("%d.%m.%Y")
    ws.append_row([member, MY_NAME, reason, date])

# ---------- РАЗРЯДЫ ----------
def get_roles_sheet():
    return sheet.worksheet("разряд")

def get_roles_data():
    ws = get_roles_sheet()
    rows = ws.get_all_values()
    return rows[1:]  # пропускаем заголовок

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

# =========================
# 🤖 INIT
# =========================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# =========================
# MENU
# =========================

def main_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📋 Список клана", callback_data="clan_list"))
    keyboard.add(InlineKeyboardButton("🎖 Разряды", callback_data="roles_menu"))
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
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())

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
    keyboard.add(
        InlineKeyboardButton("⚠ Пред", callback_data="action_pred"),
        InlineKeyboardButton("👏 Похвала", callback_data="action_praise"),
    )
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

@dp.message_handler(commands=["cancel"], state="*")
async def cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Отменено", reply_markup=main_menu())

@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    member = data["member"]
    action = data["action"]

    if action == "pred":
        append_pred(member, message.text)
        await message.answer("⚠ Пред записан", reply_markup=main_menu())
    else:
        append_praise(member, message.text)
        await message.answer("👏 Похвала записана", reply_markup=main_menu())

    await state.finish()

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
        reply_markup=main_menu()
    )

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)