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


# Время MSK
def get_msk_time():
    return datetime.now(pytz.timezone("Europe/Moscow"))


def validate_telegram_data(init_data: str) -> dict:
    """Проверяет подлинность данных от Telegram"""
    try:
        data = {}
        for pair in init_data.split("&"):
            key, value = pair.split("=", 1)
            data[key] = value

        if "hash" not in data:
            return None

        received_hash = data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

        token = os.getenv("TOKEN")
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != received_hash:
            return None

        if "user" in data:
            data["user"] = json.loads(data["user"])

        return data
    except Exception as e:
        logger.error(f"Validate error: {e}")
        return None
# Вспомогательные функции
def find_member_by_tg_id(tg_id):
    ws = sheet.worksheet("участники клана")
    rows = ws.get_all_values()
    for row in rows[1:]:
        if len(row) >= 9 and row[8].strip() == str(tg_id):
            return row[0]
    return None


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


def get_clan_members():
    ws = sheet.worksheet("участники клана")
    return [v for v in ws.col_values(1) if v.strip()]


def append_praise(member, from_user, reason):
    ws = sheet.worksheet("Похвала")
    date = get_msk_time().strftime("%d.%m.%Y")
    ws.append_row([member, from_user, reason, date])


def append_pred(member, reason):
    ws = sheet.worksheet("преды")
    date = get_msk_time().strftime("%d.%m.%Y")
    ws.append_row([member, reason, date])


def add_complaint(from_user, from_user_id, to_member, reason):
    ws = sheet.worksheet("жалобы")
    date = get_msk_time().strftime("%d.%m.%Y %H:%M")
    ws.append_row([from_user, str(from_user_id), to_member, reason, date, "активна", "", ""])


def get_complaints():
    return sheet.worksheet("жалобы").get_all_values()


def update_complaint_field(index, column, value):
    sheet.worksheet("жалобы").update_cell(index + 2, column, value)


def close_complaint(index, closed_by=None):
    update_complaint_field(index, 6, "закрыта")
    if closed_by:
        try:
            ws = sheet.worksheet("жалобы")
            timestamp = get_msk_time().strftime("%d.%m.%Y %H:%M")
            ws.update_cell(index + 2, 8, f"{closed_by} | {timestamp}")
        except:
            pass


def append_log(action, username, user_id, to_member):
    ws = sheet.worksheet("логи")
    date = get_msk_time().strftime("%d.%m.%Y %H:%M")
    ws.append_row([action, username, user_id, to_member, date])


def get_logs():
    return sheet.worksheet("логи").get_all_values()


def get_members_by_role(role):
    try:
        ws = sheet.worksheet("разряды")
        rows = ws.get_all_values()[1:]
        return [r[0] for r in rows if r[1].lower() == role]
    except:
        return []


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


def get_applications(status=None):
    try:
        ws = sheet.worksheet("Заявки на вступление")
        rows = ws.get_all_values()[1:]
        if status:
            return [row for row in rows if len(row) >= 7 and row[6] == status]
        return [row for row in rows if len(row) >= 7]
    except:
        return []


# Главная страница
@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading index.html: {e}")
        return HTMLResponse("<h1>Error loading page</h1>", status_code=500)


# Статика
app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")


# API: Авторизация
@app.post("/api/auth")
async def auth(request: Request):
    try:
        data = await request.json()
        init_data = data.get("initData", "")

        user_data = validate_telegram_data(init_data)
        if not user_data or "user" not in user_data:
            raise HTTPException(status_code=401, detail="Invalid Telegram data")

        user_id = user_data["user"]["id"]
        is_admin = user_id in ADMINS

        existing_nick = find_member_by_tg_id(user_id)
        is_registered = existing_nick is not None

        return {
            "user": user_data["user"],
            "is_admin": is_admin,
            "is_registered": is_registered,
            "nickname": existing_nick
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# API: Профиль
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


# API: Список клана
@app.get("/api/clan_members")
async def get_clan_members_api():
    try:
        members = get_clan_members()
        return {"members": members}
    except Exception as e:
        logger.error(f"Clan members error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# API: Похвала (все пользователи)
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


# API: Жалоба (все пользователи)
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


# API: Предупреждение (только админы)
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


# API: Жалобы список (админы)
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


# API: Закрыть жалобу (админы)
@app.post("/api/complaint/close")
async def close_complaint_api(request: Request, user_id: int):
    try:
        if user_id not in ADMINS:
            raise HTTPException(status_code=403, detail="Admin only")

        data = await request.json()
        index = data.get("index")
        action = data.get("action")  # "pred" или "noaction"

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
        sender_id = row[1] if len(row) > 1 else None

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


# API: Логи (админы)
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


# API: Заявки (админы)
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


# API: Статистика
@app.get("/api/stats/{period}")
async def get_stats(period: str):
    try:
        weeks = 1 if period == "week" else None
        top = get_top_praises(weeks=weeks)
        return {"top": [{"nick": m, "count": c} for m, c in top]}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# API: Разряды
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
