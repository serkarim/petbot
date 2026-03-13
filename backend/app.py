from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import gspread
import json
import os
import hmac
import hashlib
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
import pytz
from urllib.parse import unquote
import asyncio

load_dotenv()

app = FastAPI(title="PET Clan Mini App")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_data = json.loads(os.getenv("CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.getenv("SPREADSHEET_KEY"))

# Админы
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
TECH_ADMINS = list(map(int, os.getenv("TECH_ADMINS", "").split(",")))


def is_tech_admin(user_id):
    return user_id in TECH_ADMINS or user_id in ADMINS


# Время MSK
def get_msk_time():
    return datetime.now(pytz.timezone("Europe/Moscow"))


def validate_telegram_data(init_data: str):
    """Валидация данных от Telegram WebApp"""
    try:
        token = os.getenv("TOKEN")
        if not token:
            logger.error("❌ TOKEN не задан!")
            return None

        data = {}
        for item in init_data.split('&'):
            if '=' in item:
                key, value = item.split('=', 1)
                data[key] = unquote(value)

        if 'hash' not in data:
            logger.error("❌ Нет hash в initData")
            return None

        received_hash = data.pop('hash')
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != received_hash:
            logger.error(f"❌ Hash не совпадает!")
            return None

        if 'user' not in data:
            logger.error("❌ Нет user в initData")
            return None

        user_data = json.loads(data['user'])
        return user_data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга user JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка валидации: {type(e).__name__}: {e}")
        return None


# =========================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def find_member_by_tg_id(tg_id):
    try:
        ws = sheet.worksheet("участники клана")
        rows = ws.get_all_values()
        for row in rows[1:]:
            if len(row) >= 9 and row[8].strip() == str(tg_id):
                return row[0]
    except:
        pass
    return None


def get_member_info(nickname):
    try:
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
    except:
        pass
    return None


def get_clan_members():
    try:
        ws = sheet.worksheet("участники клана")
        return [v for v in ws.col_values(1) if v.strip()]
    except:
        return []


def append_praise(member, from_user, reason):
    try:
        ws = sheet.worksheet("Похвала")
        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row([member, from_user, reason, date])
    except Exception as e:
        logger.error(f"append_praise error: {e}")


def append_pred(member, reason):
    try:
        ws = sheet.worksheet("преды")
        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row([member, reason, date])
    except Exception as e:
        logger.error(f"append_pred error: {e}")


def add_complaint(from_user, from_user_id, to_member, reason):
    try:
        ws = sheet.worksheet("жалобы")
        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row([from_user, str(from_user_id), to_member, reason, date, "активна", "", ""])
    except Exception as e:
        logger.error(f"add_complaint error: {e}")


def get_complaints():
    try:
        return sheet.worksheet("жалобы").get_all_values()
    except:
        return []


def update_complaint_field(index, column, value):
    try:
        sheet.worksheet("жалобы").update_cell(index + 2, column, value)
    except:
        pass


def close_complaint(index, closed_by=None):
    try:
        update_complaint_field(index, 6, "закрыта")
        if closed_by:
            ws = sheet.worksheet("жалобы")
            timestamp = get_msk_time().strftime("%d.%m.%Y %H:%M")
            ws.update_cell(index + 2, 8, f"{closed_by} | {timestamp}")
    except:
        pass


def append_log(action, username, user_id, to_member):
    try:
        ws = sheet.worksheet("логи")
        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row([action, username, user_id, to_member, date])
    except Exception as e:
        logger.error(f"append_log error: {e}")


def get_logs():
    try:
        return sheet.worksheet("логи").get_all_values()
    except:
        return []


def get_members_by_role(role):
    try:
        ws = sheet.worksheet("разряды")
        rows = ws.get_all_values()[1:]
        return [r[0] for r in rows if len(r) > 1 and r[1].lower() == role.lower()]
    except:
        return []


def get_top_praises(weeks=None):
    try:
        ws = sheet.worksheet("Похвала")
        rows = ws.get_all_values()[1:]
        counter = {}
        for row in rows:
            if len(row) < 4 or not row[0].strip():
                continue
            member = row[0].strip()
            if weeks is not None:
                date_str = row[3].strip() if len(row) > 3 else None
                if not date_str:
                    continue
                try:
                    date = datetime.strptime(date_str, "%d.%m.%Y")
                    if date < datetime.now() - timedelta(weeks=weeks):
                        continue
                except:
                    continue
            counter[member] = counter.get(member, 0) + 1
        return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:10]
    except:
        return []


def get_applications(status=None):
    try:
        ws = sheet.worksheet("Заявки на вступление")
        rows = ws.get_all_values()[1:]
        if status:
            return [row for row in rows if len(row) >= 7 and row[6] == status]
        return [row for row in rows if len(row) >= 7]
    except:
        return []


def get_member_praises_history(nickname, limit=20):
    try:
        ws = sheet.worksheet("Похвала")
        rows = ws.get_all_values()[1:]
        praises = []
        for row in rows:
            if len(row) >= 4 and row[0].strip() == nickname.strip():
                praises.append({"from": row[1], "reason": row[2], "date": row[3]})
        return praises[-limit:]
    except:
        return []


def get_member_preds_history(nickname, limit=20):
    try:
        ws = sheet.worksheet("преды")
        rows = ws.get_all_values()[1:]
        preds = []
        for row in rows:
            if len(row) >= 3 and row[0].strip() == nickname.strip():
                preds.append({"reason": row[1], "date": row[2]})
        return preds[-limit:]
    except:
        return []


def get_available_roles():
    try:
        ws = sheet.worksheet("разряды")
        rows = ws.get_all_values()[1:]
        return list(set([r[1] for r in rows if len(r) > 1]))
    except:
        return ["сквадной", "пех", "тех", "новичок"]


def change_member_role(member, new_role, changed_by):
    try:
        ws_roles = sheet.worksheet("разряды")
        rows = ws_roles.get_all_values()
        for idx, row in enumerate(rows):
            if row and row[0] == member:
                ws_roles.update_cell(idx + 1, 2, new_role)
                break

        ws_main = sheet.worksheet("участники клана")
        rows_main = ws_main.get_all_values()
        for idx, row in enumerate(rows_main):
            if row and row[0] == member:
                ws_main.update_cell(idx + 1, 3, new_role)
                break

        append_log("СМЕНА_РАЗРЯДА", changed_by, changed_by, f"{member} → {new_role}")
        return True
    except Exception as e:
        logger.error(f"change_member_role error: {e}")
        return False


# =========================
# 📢 ОПОВЕЩЕНИЯ
# =========================
def create_notification(author_id, author_name, audience, text, schedule_time, photo_url=None):
    try:
        ws = sheet.worksheet("запланированные_оповещения")
        date_created = get_msk_time().strftime("%d.%m.%Y %H:%M")
        status = "отправлено" if schedule_time == "now" else "ожидает"
        ws.append_row([author_id, author_name, audience, text, schedule_time, date_created, status, photo_url or ""])
        return True
    except Exception as e:
        logger.error(f"create_notification error: {e}")
        try:
            ws = sheet.add_worksheet("запланированные_оповещения", rows=100, cols=8)
            ws.append_row(["author_id", "author_name", "audience", "text", "schedule_time", "date_created", "status",
                           "photo_url"])
            ws.append_row(
                [author_id, author_name, audience, text, schedule_time, date_created, status, photo_url or ""])
        except:
            pass
        return True


def get_notifications(user_id):
    try:
        ws = sheet.worksheet("запланированные_оповещения")
        rows = ws.get_all_values()[1:]

        if user_id in ADMINS or user_id in TECH_ADMINS:
            return [{"id": idx, "author": r[1], "audience": r[2], "text": r[3],
                     "schedule": r[4], "created": r[5], "status": r[6]}
                    for idx, r in enumerate(rows) if len(r) >= 7]
        else:
            return [{"id": idx, "author": r[1], "audience": r[2], "text": r[3],
                     "schedule": r[4], "created": r[5], "status": r[6]}
                    for idx, r in enumerate(rows) if len(r) >= 7 and r[6] == "отправлено"]
    except:
        return []


# =========================
# 📝 DEVLOGS
# =========================
def create_devlog(author_id, author_name, title, content, photo_url=None):
    try:
        ws = sheet.worksheet("devlogs")
        date = get_msk_time().strftime("%d.%m.%Y %H:%M")
        ws.append_row([author_id, author_name, title, content, date, "опубликовано", photo_url or ""])
        return True
    except Exception as e:
        logger.error(f"create_devlog error: {e}")
        try:
            ws = sheet.add_worksheet("devlogs", rows=100, cols=7)
            ws.append_row(["author_id", "author_name", "title", "content", "date", "status", "photo_url"])
            ws.append_row([author_id, author_name, title, content, date, "опубликовано", photo_url or ""])
        except:
            pass
        return True


def get_devlogs():
    try:
        ws = sheet.worksheet("devlogs")
        rows = ws.get_all_values()[1:]
        return [{"id": idx, "author_id": r[0], "author": r[1], "title": r[2],
                 "content": r[3], "date": r[4], "status": r[5]}
                for idx, r in enumerate(rows) if len(r) >= 6]
    except:
        return []


# =========================
# 🏆 МАССОВАЯ ПОХВАЛА
# =========================
def bulk_praise(members, from_user, reason, event_name="Ивент"):
    success = 0
    for member in members:
        try:
            append_praise(member, from_user, f"🏆 {event_name}: {reason}")
            success += 1
        except:
            pass
    return success


# =========================
# 🌐 API ENDPOINTS
# =========================

@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading index.html: {e}")
        return HTMLResponse("<h1>Error loading page</h1>", status_code=500)


app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")


@app.post("/api/auth")
async def auth(request: Request):
    try:
        data = await request.json()
        init_data = data.get("initData", "")

        if not init_data:
            raise HTTPException(status_code=400, detail="initData is required")

        user_data = validate_telegram_data(init_data)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid Telegram data")

        user = user_data.get("user", user_data)
        user_id = user.get("id")

        is_admin = user_id in ADMINS
        is_tech = is_tech_admin(user_id)
        existing_nick = find_member_by_tg_id(user_id)

        return {
            "user": user,
            "is_admin": is_admin,
            "is_tech_admin": is_tech,
            "is_registered": existing_nick is not None,
            "nickname": existing_nick
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Auth error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Server error")


@app.get("/api/profile/{user_id}")
async def get_profile(user_id: int):
    try:
        existing_nick = find_member_by_tg_id(user_id)
        if not existing_nick:
            raise HTTPException(status_code=404, detail="User not found")

        info = get_member_info(existing_nick)
        if not info:
            raise HTTPException(status_code=404, detail="Info not found")

        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clan_members")
async def get_clan_members_api():
    try:
        members = get_clan_members()
        return {"members": members}
    except Exception as e:
        logger.error(f"Clan members error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/praise")
async def send_praise(request: Request, user_id: int):
    try:
        data = await request.json()
        member = data.get("member")
        reason = data.get("reason")

        if not member or not reason:
            raise HTTPException(status_code=400, detail="Member and reason required")

        existing_nick = find_member_by_tg_id(user_id)
        from_user = existing_nick if existing_nick else f"TG:{user_id}"

        append_praise(member, from_user, reason)
        append_log("ПОХВАЛА_MINIAPP", from_user, user_id, member)

        return {"status": "ok", "message": "Похвала записана ✅"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Praise error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/complaint")
async def send_complaint(request: Request, user_id: int):
    try:
        data = await request.json()
        member = data.get("member")
        reason = data.get("reason")

        if not member or not reason:
            raise HTTPException(status_code=400, detail="Member and reason required")

        existing_nick = find_member_by_tg_id(user_id)
        from_user = existing_nick if existing_nick else f"TG:{user_id}"

        add_complaint(from_user, user_id, member, reason)
        append_log("ЖАЛОБА_MINIAPP", from_user, user_id, member)

        return {"status": "ok", "message": "Жалоба отправлена ✅"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complaint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pred")
async def send_pred(request: Request, user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        data = await request.json()
        member = data.get("member")
        reason = data.get("reason")

        if not member or not reason:
            raise HTTPException(status_code=400, detail="Member and reason required")

        existing_nick = find_member_by_tg_id(user_id)
        admin_name = existing_nick if existing_nick else f"TG:{user_id}"

        append_pred(member, reason)
        append_log("ПРЕД_MINIAPP", admin_name, user_id, member)

        return {"status": "ok", "message": "Предупреждение выдано ✅"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pred error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/complaints")
async def get_complaints_api(user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        rows = get_complaints()
        active = [r for r in rows[1:] if len(r) >= 6 and r[5] == "активна"]

        complaints = []
        for idx, r in enumerate(active):
            complaints.append({
                "index": rows.index(r) - 1,
                "from_user": r[0] if len(r) > 0 else "?",
                "from_user_id": r[1] if len(r) > 1 else "",
                "to_member": r[2] if len(r) > 2 else "?",
                "reason": r[3] if len(r) > 3 else "?",
                "date": r[4] if len(r) > 4 else "?",
                "status": r[5] if len(r) > 5 else "?",
                "proof": r[6] if len(r) > 6 else "",
                "closed_by": r[7] if len(r) > 7 else ""
            })

        return {"complaints": complaints}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complaints error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/complaint/close")
async def close_complaint_api(request: Request, user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        data = await request.json()
        index = data.get("index")
        action = data.get("action")

        if index is None or action not in ["pred", "noaction"]:
            raise HTTPException(status_code=400, detail="Invalid data")

        existing_nick = find_member_by_tg_id(user_id)
        admin_name = existing_nick if existing_nick else f"TG:{user_id}"

        rows = get_complaints()
        if index + 1 >= len(rows):
            raise HTTPException(status_code=404, detail="Complaint not found")

        row = rows[index + 1]
        violator = row[2] if len(row) > 2 else "?"
        reason = row[3] if len(row) > 3 else "?"

        if action == "pred":
            append_pred(violator, f"По жалобе: {reason}")
            append_log(f"ПРЕД_ПО_ЖАЛОБЕ_MINIAPP [{admin_name}]", admin_name, user_id, violator)

        close_complaint(index, closed_by=admin_name)

        return {"status": "ok", "message": f"Жалоба закрыта ({action}) ✅"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Close complaint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
async def get_logs_api(user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        logs = get_logs()[-20:]
        return {"logs": logs[::-1]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications")
async def get_applications_api(user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        apps = get_applications()
        return {
            "applications": [
                {
                    "id": r[0], "nick": r[1], "steam_id": r[2],
                    "tg_username": r[3], "tg_id": r[4], "date": r[5],
                    "status": r[6] if len(r) > 6 else "ожидает"
                }
                for r in apps
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Applications error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/{period}")
async def get_stats(period: str):
    try:
        weeks = 1 if period == "week" else None
        top = get_top_praises(weeks=weeks)
        return {"top": [{"nick": m, "count": c} for m, c in top]}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/roles")
async def get_roles_api():
    try:
        roles = {
            "сквадной": get_members_by_role("сквадной"),
            "пех": get_members_by_role("пех"),
            "тех": get_members_by_role("тех")
        }
        return roles
    except Exception as e:
        logger.error(f"Roles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# 🆕 НОВЫЕ API ENDPOINTS
# =========================

@app.get("/api/is_tech_admin/{user_id}")
async def check_tech_admin(user_id: int):
    return {"is_tech_admin": is_tech_admin(user_id)}


@app.post("/api/notification")
async def create_notification_api(request: Request, user_id: int):
    if user_id not in ADMINS and user_id not in TECH_ADMINS:
        raise HTTPException(status_code=403, detail="Только для админов и тех админов")

    data = await request.json()
    audience = data.get("audience")
    text = data.get("text")
    schedule_time = data.get("schedule_time", "now")
    photo_url = data.get("photo_url")

    if not audience or not text:
        raise HTTPException(status_code=400, detail="audience и text обязательны")

    existing_nick = find_member_by_tg_id(user_id)
    author_name = existing_nick if existing_nick else f"TG:{user_id}"

    create_notification(user_id, author_name, audience, text, schedule_time, photo_url)
    append_log("ОПОВЕЩЕНИЕ", author_name, user_id, audience)

    return {"status": "ok", "message": "Оповещение создано ✅"}


@app.get("/api/notifications")
async def get_notifications_api(user_id: int):
    return {"notifications": get_notifications(user_id)}


@app.post("/api/devlog")
async def create_devlog_api(request: Request, user_id: int):
    if not is_tech_admin(user_id):
        raise HTTPException(status_code=403, detail="Только для тех админов")

    data = await request.json()
    title = data.get("title")
    content = data.get("content")
    photo_url = data.get("photo_url")

    if not title or not content:
        raise HTTPException(status_code=400, detail="title и content обязательны")

    existing_nick = find_member_by_tg_id(user_id)
    author_name = existing_nick if existing_nick else f"TG:{user_id}"

    create_devlog(user_id, author_name, title, content, photo_url)

    return {"status": "ok", "message": "Devlog опубликован ✅"}


@app.get("/api/devlogs")
async def get_devlogs_api():
    return {"devlogs": get_devlogs()}


@app.get("/api/member_praises/{nickname}")
async def get_member_praises_api(nickname: str, user_id: int):
    if user_id not in ADMINS:
        raise HTTPException(status_code=403, detail="Только для админов")
    return {"praises": get_member_praises_history(nickname)}


@app.get("/api/member_preds/{nickname}")
async def get_member_preds_api(nickname: str, user_id: int):
    if user_id not in ADMINS:
        raise HTTPException(status_code=403, detail="Только для админов")
    return {"preds": get_member_preds_history(nickname)}


@app.post("/api/bulk_praise")
async def bulk_praise_api(request: Request, user_id: int):
    if user_id not in ADMINS:
        raise HTTPException(status_code=403, detail="Только для админов")

    data = await request.json()
    members = data.get("members", [])
    reason = data.get("reason", "")
    event_name = data.get("event_name", "Ивент")

    if not members or not reason:
        raise HTTPException(status_code=400, detail="members и reason обязательны")

    existing_nick = find_member_by_tg_id(user_id)
    from_user = existing_nick if existing_nick else f"TG:{user_id}"

    success = bulk_praise(members, from_user, reason, event_name)
    append_log("МАССОВАЯ_ПОХВАЛА", from_user, user_id, f"{len(members)} участников")

    return {"status": "ok", "message": f"Похвала выдана {success}/{len(members)} участникам ✅"}


@app.post("/api/change_role")
async def change_role_api(request: Request, user_id: int):
    if user_id not in ADMINS:
        raise HTTPException(status_code=403, detail="Только для админов")

    data = await request.json()
    member = data.get("member")
    new_role = data.get("role")

    if not member or not new_role:
        raise HTTPException(status_code=400, detail="member и role обязательны")

    existing_nick = find_member_by_tg_id(user_id)
    changed_by = existing_nick if existing_nick else f"TG:{user_id}"

    if change_member_role(member, new_role, changed_by):
        return {"status": "ok", "message": f"Разряд изменён на {new_role} ✅"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка смены разряда")


@app.get("/api/available_roles")
async def get_available_roles_api():
    return {"roles": get_available_roles()}


# # Запуск
# if __name__ == "__main__":
#     import uvicorn
#
#     uvicorn.run(app, host="0.0.0.0", port=8000)