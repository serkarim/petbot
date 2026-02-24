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
                'desirable': row[6] if len(row) > 6 else 'N/A'
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

# ---------- ЖАЛОБЫ (С РАСШИРЕННЫМ ЛОГИРОВАНИЕМ) ----------

def add_complaint(from_user, from_user_id, to_member, reason):
    ws = sheet.worksheet("жалобы")
    date = datetime.now().strftime("%d.%m.%Y %H:%M")
    # [От кого, ID, На кого, Причина, Дата, Статус, Доки, Закрыл]
    ws.append_row([from_user, str(from_user_id), to_member, reason, date, "активна", "", ""])

def get_complaints():
    ws = sheet.worksheet("жалобы")
    return ws.get_all_values()

def update_complaint_field(index, column, value):
    ws = sheet.worksheet("жалобы")
    ws.update_cell(index + 2, column, value)

def close_complaint(index, closed_by=None):
    """Закрывает жалобу + записывает кто закрыл в 8-ю колонку"""
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
    waiting_proof = State()

# =========================
# START / CANCEL / BACK
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu(message.from_user.id))

@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu(callback.from_user.id))

@dp.message_handler(state='*', commands=['cancel'])
async def cancel_handler(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return
    await state.finish()
    await message.answer("✅ Действие отменено", reply_markup=main_menu(message.from_user.id))

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
        await callback.message.edit_text(f"✅ Роль для {member} обновлена на {new_role}", reply_markup=main_menu(callback.from_user.id))
    else:
        await callback.message.edit_text("❌ Ошибка: участник не найден")

# =========================
# 📊 СТАТИСТИКА
# =========================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    top = get_top_week()
    text = "📭 За 7 дней похвал ещё нет." if not top else (
        "🏆 ТОП-5 за неделю:\n\n" + "\n".join(f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
    await callback.message.edit_text(text, reply_markup=keyboard)

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
        text = "🕒 Последние 10 действий:\n\n" + "\n".join(
            f"`{row[4]}` | {row[0]} | {row[1]} → {row[3]}"
            for row in logs_data[-1:0:-1] if len(row) >= 5
        )

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
# ⚖ ЖАЛОБЫ (С ЛОГИРОВАНИЕМ ДЕЙСТВИЙ)
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

    # === 1. ПРЕД + ЗАКРЫТЬ ===
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
        # 🔥 Логируем с указанием АДМИНА
        append_log(f"ПРЕД_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, violator)
        close_complaint(index, closed_by=admin_info)

        if sender_id:
            try:
                await bot.send_message(int(sender_id), f"✅ Жалоба на {violator} рассмотрена. Выдан ПРЕД.", parse_mode="HTML")
            except:
                pass
        await callback.message.edit_text(f"⚠ ПРЕД выдан {violator}. Жалоба закрыта ✅", reply_markup=main_menu(callback.from_user.id))
        return

    # === 2. ЗАПРОС ДОКОВ ===
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

        # 🔥 Логируем запрос доказательств
        append_log(f"ЗАПРОС_ДОКОВ_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, target)

        if sender_id:
            try:
                await dp.storage.set_state(chat=int(sender_id), user=int(sender_id), state=ActionState.waiting_proof)
                await dp.storage.set_data(chat=int(sender_id), user=int(sender_id), data={"complaint_index": index, "admin_id": callback.from_user.id})
                await bot.send_message(int(sender_id), f"🔍 Запрошены доказательства по жалобе на {target}.\nОтправьте скриншоты или /cancel", parse_mode="HTML")
                await callback.answer("📩 Запрос отправлен", show_alert=True)
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
        else:
            await callback.answer("❌ Не найден ID", show_alert=True)
        return

    # === 3. ЗАКРЫТЬ БЕЗ ДЕЙСТВИЙ ===
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

        # 🔥 Логируем закрытие без санкций
        append_log(f"ЖАЛОБА_ЗАКРЫТА_БЕЗ_ДЕЙСТВИЙ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, target)
        close_complaint(index, closed_by=admin_info)

        if sender_id:
            try:
                await bot.send_message(int(sender_id), f"ℹ️ Жалоба на {target} закрыта без санкций.", parse_mode="HTML")
            except:
                pass
        await callback.message.edit_text(f"✅ Жалоба закрыта", reply_markup=main_menu(callback.from_user.id))
        return

    # === 4. ПРОСМОТР ===
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
# 🚀 START
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)