import logging
from datetime import datetime, timedelta
import os
import json
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
import pytz

# =========================
# 🔐 ENV (ИСПРАВЛЕНО: убраны пробелы в названиях ключей)
# =========================
TOKEN = os.getenv("TOKEN")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID")
REPORT_TOPIC_ID = os.getenv("REPORT_TOPIC_ID")
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
                'id': row[0], 'nick': row[1], 'steam_id': row[2],
                'tg_username': row[3], 'tg_id': row[4], 'date': row[5],
                'status': row[6] if len(row) > 6 else 'ожидает'
            }
    return None


def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    ws.append_row([member, reason, datetime.now().strftime("%d.%m.%Y")])


def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    ws.append_row([member, from_user, reason, datetime.now().strftime("%d.%m.%Y")])


def append_log(action, username, user_id, to_member):
    ws = sheet.worksheet("логи")
    ws.append_row([action, username, user_id, to_member, datetime.now().strftime("%d.%m.%Y %H:%M")])


def get_logs():
    return sheet.worksheet("логи").get_all_values()


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
    return [{"id": r[0], "name": r[1], "text": r[2], "active": r[3].lower() == "да"} for r in rows if
            len(r) >= 4 and r[0].strip()]


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
    top_text = "📭 На этой неделе похвал ещё нет. Давайте активнее! 🔥" if not top else "\n".join(
        f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
    return template["text"].format(top_list=top_text, date=datetime.now().strftime("%d.%m.%Y"),
                                   week_start=(datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y"))


async def send_weekly_report():
    if not REPORT_CHAT_ID:
        logging.warning("REPORT_CHAT_ID не задан")
        return
    report_text = generate_weekly_report()
    try:
        if REPORT_TOPIC_ID and REPORT_TOPIC_ID.isdigit():
            await bot.send_message(chat_id=REPORT_CHAT_ID, text=report_text, parse_mode="HTML",
                                   message_thread_id=int(REPORT_TOPIC_ID))
        else:
            await bot.send_message(chat_id=REPORT_CHAT_ID, text=report_text, parse_mode="HTML")
        logging.info("✅ Еженедельный отчёт отправлен")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки отчёта: {e}")


def add_complaint(from_user, from_user_id, to_member, reason):
    ws = sheet.worksheet("жалобы")
    ws.append_row(
        [from_user, str(from_user_id), to_member, reason, datetime.now().strftime("%d.%m.%Y %H:%M"), "активна", "", ""])


def get_complaints():
    return sheet.worksheet("жалобы").get_all_values()


def update_complaint_field(index, column, value):
    sheet.worksheet("жалобы").update_cell(index + 2, column, value)


def close_complaint(index, closed_by=None):
    update_complaint_field(index, 6, "закрыта")
    if closed_by:
        try:
            ws = sheet.worksheet("жалобы")
            ws.update_cell(index + 2, 8, f"{closed_by} | {datetime.now().strftime('%d.%m.%Y %H:%M')}")
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
        keyboard.add(InlineKeyboardButton("📬 Заявки", callback_data="applications_menu"))

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
    reg_type_choice = State()
    reg_rules = State()
    reg_steam_nick = State()
    reg_steam_id = State()
    reg_confirm = State()
    reg_select_existing = State()
    reg_existing_confirm = State()


# =========================
# START / CANCEL / BACK
# =========================
@dp.message_handler(commands=["start"])
async def start(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        existing_nick = find_member_by_tg_id(user_id)
        if existing_nick:
            safe_nick = html_lib.escape(existing_nick)
            await message.answer(f"👋 С возвращением, {username}!\n✅ Вы уже зарегистрированы как {safe_nick}",
                                 reply_markup=main_menu(user_id, is_registered=True), parse_mode="HTML")
        else:
            apps = get_applications(status="ожидает")
            has_pending = any(app[4] == str(user_id) for app in apps)
            await state.update_data(tg_username=username, tg_id=user_id)
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("📝 Подать заявку", callback_data="apply_start"))
            if has_pending:
                keyboard.add(InlineKeyboardButton("📋 Статус заявки", callback_data="app_status"))
            await message.answer(
                f"👋 Привет, {username}!\nЧтобы вступить в клан:\n1️⃣ Подать заявку\n2️⃣ Дождаться проверки\n3️⃣ Получить ссылку\nГотовы?",
                reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ start: {e}")


@dp.callback_query_handler(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        apps = get_applications(status="ожидает")
        has_pending = any(app[4] == str(user_id) for app in apps)
        await callback.message.edit_text("Главное меню:",
                                         reply_markup=main_menu(user_id, is_registered=(existing_nick is not None),
                                                                has_pending_app=has_pending))
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ back_menu: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.message_handler(state='*', commands=['cancel'])
async def cancel_handler(message: types.Message, state: FSMContext):
    try:
        if await state.get_state() is None:
            return
        await state.finish()
        await message.answer("✅ Действие отменено", reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        logging.error(f"❌ cancel: {e}")


# =========================
# 📝 РЕГИСТРАЦИЯ (ПОЛНОСТЬЮ ЧИСТЫЙ КОД)
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

        await callback.message.edit_text(
            "🔍 Выберите вариант:\n🆕 Новенький — подайте заявку на вступление\n👤 Уже в клане — привяжите аккаунт к существующему нику",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ apply_start: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "reg_type_new")
async def reg_type_new(callback: types.CallbackQuery, state: FSMContext):
    try:
        await ActionState.reg_rules.set()
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Согласен с правилами", callback_data="rules_accept"),
            InlineKeyboardButton("❌ Отмена", callback_data="apply_start")
        )
        await callback.message.edit_text(
            "📜 Правила клана PET\n1️⃣ Уважение ко всем участникам\n2️⃣ Запрет на читы\n3️⃣ Активность в клане\n4️⃣ Выполнение приказов\n5️⃣ Конфиденциальность\n⚠️ Нарушение = предупреждение или кик!\nСогласны?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ reg_type_new: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "rules_accept")
async def rules_accepted(callback: types.CallbackQuery, state: FSMContext):
    try:
        await ActionState.reg_steam_nick.set()
        await callback.message.edit_text("🆕 Введите ваш никнейм в Steam (как в игре):\nПример: [PET] КИРЮХА",
                                         parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ rules_accepted: {e}")


@dp.message_handler(state=ActionState.reg_steam_nick)
async def reg_save_steam_nick(message: types.Message, state: FSMContext):
    try:
        await state.update_data(steam_nick=message.text.strip())
        await ActionState.reg_steam_id.set()
        await message.answer("🎮 Введите Steam ID (64-bit):\nПример: 76561198984240881\nКак узнать: https://steamid.io/",
                             parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ reg_save_steam_nick: {e}")


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

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Подтвердить заявку", callback_data="app_submit"),
            InlineKeyboardButton("❌ Изменить", callback_data="reg_type_new")
        )
        await message.answer(
            f"📋 Проверьте данные:\n🎮 Ник: `{data['steam_nick']}`\n🆔 Steam ID: `{steam_id}`\n👤 TG: `{message.from_user.full_name}`\nВсё верно?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"❌ reg_save_steam_id: {e}")


@dp.callback_query_handler(lambda c: c.data == "app_submit")
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
                kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
                )
                await bot.send_message(
                    admin_id,
                    f"📬 Новая заявка!\n🆔 #{app_id}\n🎮 `{steam_nick}`\n🆔 `{steam_id}`\n👤 {tg_username}\n🆔 `{tg_id}`\n🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"❌ Ошибка уведомления админа: {e}")

        await callback.message.edit_text(
            f"✅ Заявка отправлена!\n📋 ID: `#{app_id}`\nОжидайте решения модераторов!",
            reply_markup=main_menu(tg_id, has_pending_app=True),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ app_submit: {e}")
        await callback.answer("❌ Ошибка отправки", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "reg_type_existing")
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
            await callback.message.edit_text(
                "✅ Все участники уже зарегистрированы!",
                reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="apply_start")),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # 🔥 СОХРАНЯЕМ СПИСОК В FSM
        await state.update_data(unregistered_list=unregistered)

        keyboard = InlineKeyboardMarkup(row_width=2)
        for idx, nick in enumerate(unregistered[:30]):
            # 🔥 ИСПРАВЛЕНО: Нет пробелов в callback_data
            keyboard.add(InlineKeyboardButton(nick, callback_data=f"reg_sel_{idx}"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="apply_start"))

        await callback.message.edit_text(
            f"👤 Выберите ваш никнейм\nНайдено {len(unregistered)} участников без регистрации:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ reg_type_existing: {e}")
        await callback.answer("❌ Ошибка загрузки списка", show_alert=True)


@dp.callback_query_handler(lambda c: c.data.startswith("reg_sel_"))
async def reg_select_existing(callback: types.CallbackQuery, state: FSMContext):
    try:
        # 🔥 ИСПРАВЛЕНО: Заменяем на пустую строку, без пробелов
        idx_str = callback.data.replace("reg_sel_", "", 1)

        if not idx_str.isdigit():
            await callback.answer("❌ Ошибка индекса", show_alert=True)
            return

        idx = int(idx_str)
        data = await state.get_data()
        unregistered = data.get("unregistered_list", [])

        # 🔥 ПРОВЕРКА: Если список потерялся, загружаем заново
        if not unregistered:
            ws = sheet.worksheet("участники клана")
            rows = ws.get_all_values()[1:]
            unregistered = []
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

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Да, это я!", callback_data="reg_existing_yes"),
            InlineKeyboardButton("❌ Нет, другой", callback_data="reg_type_existing")
        )

        safe_nickname = html_lib.escape(nickname)
        await callback.message.edit_text(
            f"🔍 Подтверждение\nВы выбираете: {safe_nickname}\nЭто правильный ник?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ reg_select_existing: {e}")
        await callback.answer("❌ Ошибка при выборе ника", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "reg_existing_yes")
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
                f"⚠️ Ваш TG уже привязан!\nВы зарегистрированы как: {safe_existing}",
                reply_markup=main_menu(tg_id, is_registered=True),
                parse_mode="HTML"
            )
            await state.finish()
            return

        if update_member_tg_data(nickname, tg_username, tg_id):
            append_log("РЕГИСТРАЦИЯ_УЧАСТНИК", tg_username, tg_id, nickname)
            await state.finish()
            safe_nick = html_lib.escape(nickname)
            await callback.message.edit_text(
                f"✅ Регистрация завершена!\nВы привязаны к: {safe_nick}\nТеперь доступны все функции!",
                reply_markup=main_menu(tg_id, is_registered=True),
                parse_mode="HTML"
            )
        else:
            await callback.answer("❌ Ошибка обновления данных", show_alert=True)

        await callback.answer()
    except Exception as e:
        logging.error(f"❌ reg_existing_confirm: {e}")
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

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu")),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ app_status: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# =========================
# 📬 АДМИН-ПАНЕЛЬ ЗАЯВОК
# =========================
@dp.callback_query_handler(lambda c: c.data == "applications_menu")
async def applications_menu(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌ Только для админов", show_alert=True)
            return

        apps = get_applications(status="ожидает")
        keyboard = InlineKeyboardMarkup()
        if not apps:
            keyboard.add(InlineKeyboardButton("📭 Нет заявок", callback_data="none"))
        else:
            for app in apps:
                keyboard.add(InlineKeyboardButton(f"📬 #{app[0]} | {app[1]}", callback_data=f"app_view_{app[0]}"))

        keyboard.add(
            InlineKeyboardButton("🟢 Принятые", callback_data="apps_accepted"),
            InlineKeyboardButton("🔴 Отклонённые", callback_data="apps_rejected"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text(f"📬 Заявки\n🟡 Ожидает: {len(apps)}", reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ applications_menu: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("app_"))
async def app_actions(callback: types.CallbackQuery):
    try:
        if callback.from_user.id not in ADMINS:
            await callback.answer("❌", show_alert=True)
            return

        parts = callback.data.split("_")
        action = parts[1] if len(parts) > 1 else ""

        if action == "view":
            app_id = parts[2] if len(parts) > 2 else None
            app = get_application_by_id(app_id) if app_id else None
            if not app:
                await callback.answer("❌ Не найдено", show_alert=True)
                return

            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("✅ Принять", callback_data=f"app_accept_{app_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"app_reject_{app_id}")
            ).add(InlineKeyboardButton("🔙 Назад", callback_data="applications_menu"))

            text = f"📬 Заявка #{app['id']}\n🎮 `{app['nick']}`\n🆔 `{app['steam_id']}`\n👤 {app['tg_username']}\n🆔 `{app['tg_id']}`\n🕒 {app['date']}\n🟡 {app['status']}"
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return

        if action == "accept":
            app_id = parts[2] if len(parts) > 2 else None
            app = get_application_by_id(app_id) if app_id else None
            if not app:
                await callback.answer("❌ Не найдено", show_alert=True)
                return

            update_application_status(app_id, "принят")
            if add_new_member(app['nick'], app['steam_id'], app['tg_username'], app['tg_id']):
                try:
                    await bot.send_message(int(app['tg_id']),
                                           f"🎉 Заявка принята!\nДобро пожаловать в PET!\n🔗 {GROUP_LINK}",
                                           parse_mode="HTML")
                except:
                    pass
                append_log("ЗАЯВКА_ПРИНЯТА", callback.from_user.full_name, callback.from_user.id, app['nick'])
                await callback.answer("✅ Принято! Участник добавлен", show_alert=True)
            else:
                await callback.answer("⚠️ Уже существует", show_alert=True)
            await applications_menu(callback)
            return

        if action == "reject":
            app_id = parts[2] if len(parts) > 2 else None
            app = get_application_by_id(app_id) if app_id else None
            if not app:
                await callback.answer("❌ Не найдено", show_alert=True)
                return

            update_application_status(app_id, "отклонен")
            try:
                await bot.send_message(int(app['tg_id']), "❌ Заявка отклонена\nПопробуйте через 7 дней.",
                                       parse_mode="HTML")
            except:
                pass
            append_log("ЗАЯВКА_ОТКЛОНЕНА", callback.from_user.full_name, callback.from_user.id, app['nick'])
            await callback.answer("❌ Отклонено", show_alert=True)
            await applications_menu(callback)
            return

        if action in ["accepted", "rejected"]:
            status = "принят" if action == "accepted" else "отклонен"
            apps = get_applications(status=status)
            kb = InlineKeyboardMarkup()
            for app in apps[:10]:
                kb.add(InlineKeyboardButton(f"#{app[0]} | {app[1]}", callback_data=f"app_view_{app[0]}"))
            kb.add(InlineKeyboardButton("🔙 Назад", callback_data="applications_menu"))

            await callback.message.edit_text(
                f"{'🟢' if action == 'accepted' else '🔴'} {'Принятые' if action == 'accepted' else 'Отклонённые'}\nВсего: {len(apps)}",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return

        await callback.answer("❌ Неизвестное действие", show_alert=True)
    except Exception as e:
        logging.error(f"❌ app_actions: {e}")


# =========================
# 👤 ПРОФИЛЬ
# =========================
@dp.callback_query_handler(lambda c: c.data == "my_profile")
async def my_profile(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        existing_nick = find_member_by_tg_id(user_id)
        if not existing_nick:
            await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
            return

        info = get_member_info(existing_nick)
        if not info:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return

        status_emoji = "✅" if info['desirable'] == "желателен" else "❌"
        safe_nick = html_lib.escape(info['nick'])
        text = f"👤 Ваш профиль\n🎮 {safe_nick}\n🆔 `{info['steam_id']}`\n🎖 {info['role']}\n⚠️ {info['warns']}\n👏 {info['praises']}\n📊 {info['score']}\n📌 {status_emoji} {info['desirable']}\n🆔 `{user_id}`"

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu")),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ my_profile: {e}")


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
        if is_admin:
            kb.add(InlineKeyboardButton("⚠ Пред", callback_data="action_pred"))

            if info:
                emoji = "✅" if info['desirable'] == "желателен" else "❌"
                safe_nick = html_lib.escape(info['nick'])
                text = f"👤 Карточка: {safe_nick}\n🎮 Steam: `{info['steam_id']}`\n🎖 Роль: {info['role']}\n⚠️ Предупреждения: {info['warns']}\n👏 Похвалы: {info['praises']}\n📊 Рейтинг: {info['score']}\n📌 Статус: {emoji} {info['desirable']}\nВыберите действие:"
            else:
                safe_member = html_lib.escape(member)
                text = f"⚠️ Участник {safe_member}\nИнформация не найдена.\nВыберите действие:"
        else:
            safe_member = html_lib.escape(member)
            text = f"👤 Участник: {safe_member}\nВыберите действие:"

    kb.add(
        InlineKeyboardButton("👏 Похвала", callback_data="action_praise"),
        InlineKeyboardButton("⚖ Жалоба", callback_data="action_complaint"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

except Exception as e:
logging.error(f"❌ member_selected: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("action_"))
async def action_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        action = callback.data.replace("action_", "")
        await state.update_data(action=action)
        await ActionState.waiting_reason.set()
        await callback.message.answer(
            "📝 Опиши причину (или /cancel):" if action == "complaint" else "📝 Напиши причину (или /cancel):")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ action_selected: {e}")


@dp.message_handler(state=ActionState.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        member = data.get("member")
        action = data.get("action")
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
    except Exception as e:
        logging.error(f"❌ process_reason: {e}")


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
# 🎖 РАЗРЯДЫ
# =========================
@dp.callback_query_handler(lambda c: c.data == "roles_menu")
async def roles_menu(callback: types.CallbackQuery):
    try:
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton(f"🪖 Сквадные ({count_by_role('сквадной')})", callback_data="role_сквадной"),
            InlineKeyboardButton(f"🎯 Пехи ({count_by_role('пех')})", callback_data="role_пех"),
            InlineKeyboardButton(f"🔧 Техи ({count_by_role('тех')})", callback_data="role_тех"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )
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
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🪖 Сквадной", callback_data="setrole_сквадной"),
            InlineKeyboardButton("🎯 Пех", callback_data="setrole_пех"),
            InlineKeyboardButton("🔧 Тех", callback_data="setrole_тех"),
            InlineKeyboardButton("⬅ Назад", callback_data="roles_menu")
        )
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
            await callback.message.edit_text(f"✅ Роль для {safe_member} обновлена на {new_role}",
                                             reply_markup=main_menu(callback.from_user.id))
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
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📅 За неделю", callback_data="stats_week"),
            InlineKeyboardButton("📈 За всё время", callback_data="stats_all"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )
        await callback.message.edit_text("📊 Выберите период:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats: {e}")


@dp.callback_query_handler(lambda c: c.data == "stats_week")
async def stats_week(callback: types.CallbackQuery):
    try:
        top = get_top_praises(weeks=1)
        text = "📭 За неделю похвал ещё нет." if not top else "🏆 ТОП-10 за неделю:\n" + "\n".join(
            f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Назад", callback_data="stats"),
                InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
            ),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats_week: {e}")


@dp.callback_query_handler(lambda c: c.data == "stats_all")
async def stats_all(callback: types.CallbackQuery):
    try:
        top = get_top_praises(weeks=None)
        text = "📭 Похвал ещё нет." if not top else "🏆 ТОП-10 за всё время:\n" + "\n".join(
            f"{i}. {m} — {c} 👏" for i, (m, c) in enumerate(top, 1))
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Назад", callback_data="stats"),
                InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
            ),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ stats_all: {e}")


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
            kb.add(InlineKeyboardButton(f"{'✅' if t['active'] else '⭕'} {t['name']}",
                                        callback_data=f"tmpl_view_{t['id']}"))

        kb.add(
            InlineKeyboardButton("➕ Добавить", callback_data="tmpl_add"),
            InlineKeyboardButton("🔄 Тест", callback_data="tmpl_test"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text("📄 Шаблоны отчётов\nЗелёная галочка = активный", reply_markup=kb,
                                         parse_mode="HTML")
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

            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("✏️ Текст", callback_data=f"tmpl_edit_text_{tid}"),
                InlineKeyboardButton("🔄 Активировать" if not tmpl["active"] else "✅ Активен",
                                     callback_data=f"tmpl_activate_{tid}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"tmpl_delete_{tid}"),
                InlineKeyboardButton("🔙 Назад", callback_data="templates_menu")
            )
            preview = tmpl["text"][:200] + "..." if len(tmpl["text"]) > 200 else tmpl["text"]
            await callback.message.edit_text(
                f"📄 {tmpl['name']}\n`{preview}`\n🔁 {'✅ Активен' if tmpl['active'] else '⭕ Не активен'}",
                reply_markup=kb,
                parse_mode="HTML"
            )
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
            kb.add(InlineKeyboardButton(f"{'✅' if t['active'] else '⭕'} {t['name']}",
                                        callback_data=f"tmpl_view_{t['id']}"))
        kb.add(
            InlineKeyboardButton("➕ Добавить", callback_data="tmpl_add"),
            InlineKeyboardButton("🔄 Тест", callback_data="tmpl_test"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )
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
        await message.answer("✅ Обновлено!", reply_markup=main_menu(message.from_user.id))
        await state.finish()
    except Exception as e:
        logging.error(f"❌ save_template_text: {e}")


@dp.message_handler(state=ActionState.new_template_name)
async def save_template_name(message: types.Message, state: FSMContext):
    try:
        await state.update_data(new_template_name=message.text)
        await ActionState.new_template_text.set()
        await message.answer("📝 Теперь введите текст шаблона:")
    except Exception as e:
        logging.error(f"❌ save_template_name: {e}")


@dp.message_handler(state=ActionState.new_template_text)
async def save_new_template(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        name = data.get("new_template_name")
        text = message.text
        if not name or not text:
            await message.answer("❌ Ошибка")
            await state.finish()
            return
        new_id = add_template(name, text)
        user = message.from_user
        username = f"@{user.username}" if user.username else user.full_name
        append_log("СОЗДАНИЕ_ШАБЛОНА", username, user.id, f"Шаблон '{name}' ID:{new_id}")
        await message.answer(f"✅ Создан! ID: {new_id}", reply_markup=main_menu(message.from_user.id))
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
                    action = row[0].replace("`", "\\`")
                    username = row[1].replace("`", "\\`")
                    target = row[3].replace("`", "\\`")
                    date = row[4].replace("`", "\\`")
                    text += f"`{date}` | {action} | {username} → {target}\n"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🗑 Очистить логи", callback_data="clear_logs"))
        keyboard.add(InlineKeyboardButton("🏠 В меню", callback_data="back_menu"))
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ logs: {e}")


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
                kb.add(InlineKeyboardButton(f"🔴 {r[2] if len(r) > 2 else '?'}",
                                            callback_data=f"complaint_{rows.index(r) - 1}"))

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
            violator = row[2] if len(row) > 2 else "?"
            reason = row[3] if len(row) > 3 else "?"
            sender_id = row[1] if len(row) > 1 else None

            append_pred(violator, f"По жалобе: {reason}")
            append_log(f"ПРЕД_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id, violator)
            close_complaint(idx, closed_by=admin_info)

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
                idx = int(data[3])
            except:
                return await callback.answer("❌ Ошибка", show_alert=True)
            rows = get_complaints()
            if idx + 1 >= len(rows):
                return await callback.answer("❌ Не найдено", show_alert=True)
            row = rows[idx + 1]
            sender_id = row[1] if len(row) > 1 else None
            target = row[2] if len(row) > 2 else "?"

            append_log(f"ЗАПРОС_ДОКОВ_ПО_ЖАЛОБЕ [{admin_info}]", callback.from_user.full_name, callback.from_user.id,
                       target)

            if sender_id:
                try:
                    await dp.storage.set_state(chat=int(sender_id), user=int(sender_id),
                                               state=ActionState.waiting_proof)
                    await dp.storage.set_data(chat=int(sender_id), user=int(sender_id),
                                              data={"complaint_index": idx, "admin_id": callback.from_user.id})
                    await bot.send_message(int(sender_id), f"🔍 Запрошены доказательства по жалобе на {target}.",
                                           parse_mode="HTML")
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
            sender_id = row[1] if len(row) > 1 else None
            target = row[2] if len(row) > 2 else "?"

            append_log(f"ЖАЛОБА_ЗАКРЫТА_БЕЗ_ДЕЙСТВИЙ [{admin_info}]", callback.from_user.full_name,
                       callback.from_user.id, target)
            close_complaint(idx, closed_by=admin_info)

            if sender_id:
                try:
                    await bot.send_message(int(sender_id), f"ℹ️ Жалоба на {target} закрыта без санкций.",
                                           parse_mode="HTML")
                except:
                    pass

            await callback.message.edit_text("✅ Жалоба закрыта", reply_markup=main_menu(callback.from_user.id))
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

        kb = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("⚠ ПРЕД + закрыть", callback_data=f"complaint_pred_{idx}"),
            InlineKeyboardButton("📸 Запросить доки", callback_data=f"complaint_request_proof_{idx}"),
            InlineKeyboardButton("❌ Закрыть (ничего)", callback_data=f"complaint_close_noaction_{idx}"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_menu")
        )

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ complaint_actions: {e}")


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
# 🚀 START (ИСПРАВЛЕНО)
# =========================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)