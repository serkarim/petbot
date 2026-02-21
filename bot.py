import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import gspread
from oauth2client.service_account import ServiceAccountCredentials
# =========================
# 🔐 НАСТРОЙКИ
# =========================


import os
import json

creds_data = json.loads(os.getenv("CREDS_JSON"))
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
TOKEN = os.getenv("TOKEN")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
MY_NAME = os.getenv("MY_NAME")
MY_NAME = "BOT"
CLAN_MEMBERS = [
    "mарселль",
    "жирпуз",
    "ГОЙДАР Amoral"
]

# =========================
# 📊 Google Sheets
# =========================
# =========================
# 📊 Google Sheets
# =========================


client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_KEY)


def get_clan_members():
    ws = sheet.worksheet("участники клана")
    return [v for v in ws.col_values(1) if v.strip()]


def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = datetime.now().strftime("%d%m%y")
    ws.append_row([member, reason, date])


def append_praise(member, reason):
    ws = sheet.worksheet("Похвала")
    date = datetime.now().strftime("%d%m%y")
    ws.append_row([member, MY_NAME, reason, date])


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
    return keyboard


# =========================
# FSM
# =========================

class ActionState(StatesGroup):
    waiting_reason = State()


# =========================
# 🏠 Главное меню
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu())


@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())


# =========================
# 📋 Список клана
# =========================

@dp.callback_query_handler(lambda c: c.data == "clan_list")
async def clan_list(callback: types.CallbackQuery):
    members = get_clan_members()

    keyboard = InlineKeyboardMarkup(row_width=2)
    for m in members:
        keyboard.insert(InlineKeyboardButton(m, callback_data=f"member_{m}"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    try:
        await callback.message.edit_text("Выбери участника:", reply_markup=keyboard)
    except:
        await callback.message.answer("Выбери участника:", reply_markup=keyboard)


# =========================
# 👤 Выбор участника
# =========================

@dp.callback_query_handler(lambda c: c.data.startswith("member_"))
async def member_selected(callback: types.CallbackQuery, state: FSMContext):
    member = callback.data.replace("member_", "")
    await state.update_data(member=member)

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("⚠ Пред", callback_data="action_pred"),
        InlineKeyboardButton("👏 Похвала", callback_data="action_praise"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
    )

    await callback.message.edit_text(
        f"Выбран: {member}\n\nВыбери действие:",
        reply_markup=keyboard
    )


# =========================
# 🎯 Выбор действия
# =========================

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
    await message.answer("Отменено", reply_markup=main_menu())


# =========================
# ✍ Запись в таблицу
# =========================

@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()

    member = data["member"]
    action = data["action"]
    reason = message.text

    if action == "pred":
        append_pred(member, reason)
        await message.answer("⚠ Пред записан", reply_markup=main_menu())
    else:
        append_praise(member, reason)
        await message.answer("👏 Похвала записана", reply_markup=main_menu())

    await state.finish()


# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)