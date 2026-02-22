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
        if row and row[0] == member:
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

# ---------- ЖАЛОБЫ (строки) ----------
def add_complaint(from_user, to_member, reason):
    ws = sheet.worksheet("жалобы")
    date = datetime.now().strftime("%d.%m.%Y %H:%M")
    ws.append_row([from_user, to_member, reason, date, "активна"])

def get_complaints():
    ws = sheet.worksheet("жалобы")
    return ws.get_all_values()

def close_complaint(index):
    ws = sheet.worksheet("жалобы")
    ws.update_cell(index + 1, 5, "закрыта")

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

    if action == "complaint":
        await callback.message.answer("Опиши жалобу:")
    else:
        await callback.message.answer("Напиши причину (или /cancel):")

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
        append_log("ЖАЛОБА", username, user_id, member)
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
# 📊 СТАТИСТИКА
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    top = get_top_week()

    text = "За 7 дней похвалы нет." if not top else (
        "🏆 ТОП 5 за неделю:\n\n" +
        "\n".join(f"{i}. {m} — {c}" for i,(m,c) in enumerate(top,1))
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard)

# =========================
# 📝 ЛОГИ
# =========================

@dp.callback_query_handler(lambda c: c.data == "logs")
async def logs(callback: types.CallbackQuery):
    logs_data = get_logs()[-10:]

    text = "Последние 10 действий:\n\n" + "\n".join(" | ".join(row) for row in logs_data)

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs"))
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "clear_logs")
async def clear_logs_handler(callback: types.CallbackQuery):
    clear_logs()
    await callback.message.edit_text("Логи очищены ✅", reply_markup=main_menu(callback.from_user.id))

# =========================
# ⚖ ЖАЛОБЫ (строки)
# =========================

@dp.callback_query_handler(lambda c: c.data == "complaints")
async def complaints_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Только для админов ❌")
        return

    rows = get_complaints()
    keyboard = InlineKeyboardMarkup()

    for i, row in enumerate(rows):
        if len(row) < 5:
            row += ["активна"]

        status = row[4]
        keyboard.add(InlineKeyboardButton(
            f"⚖ {row[1]} | {status}",
            callback_data=f"complaint_{i}"
        ))

    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))

    await callback.message.edit_text("Жалобы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("complaint_"))
async def complaint_actions(callback: types.CallbackQuery):
    data = callback.data.split("_")

    # закрытие жалобы
    if data[1] == "close":
        try:
            index = int(data[2])
        except:
            await callback.answer("Ошибка ❌")
            return

        close_complaint(index)
        await callback.message.edit_text("Жалоба закрыта ✅")
        return

    # открытие жалобы
    try:
        index = int(data[1])
    except:
        await callback.answer("Ошибка ❌")
        return

    rows = get_complaints()
    if index >= len(rows):
        await callback.answer("Не найдена ❌")
        return

    row = rows[index]
    if len(row) < 5:
        row += ["активна"]

    text = (
        f"⚖ ЖАЛОБА #{index}\n"
        f"От: {row[0]}\n"
        f"На: {row[1]}\n"
        f"Причина: {row[2]}\n"
        f"Дата: {row[3]}\n"
        f"Статус: {row[4]}"
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            "❌ Закрыть",
            callback_data=f"complaint_close_{index}"
        )
    )
    keyboard.add(
        InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
    )

    await callback.message.edit_text(text, reply_markup=keyboard)

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)