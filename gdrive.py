# gdrive.py
import os
import io
import base64
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload

# Настройки
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = 'credentials.json'


def get_drive_service():
    """Инициализация сервиса Google Drive"""
    try:
        creds_b64 = os.getenv('GDRIVE_CREDENTIALS_B64')

        if creds_b64:
            creds_data = base64.b64decode(creds_b64)
            with open('credentials.json', 'wb') as f:
                f.write(creds_data)

        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            logging.error("❌ credentials.json не найден!")
            raise FileNotFoundError("credentials.json not found")

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации Drive сервиса: {e}")
        raise


def upload_video_to_drive(file_bytes: bytes, filename: str, description: str = "") -> dict:
    """
    Загружает видео на Google Drive
    Важно: file_bytes должен быть типом bytes, а не BytesIO
    """
    try:
        service = get_drive_service()
        folder_id = os.getenv('GDRIVE_FOLDER_ID')

        # 🔥 Проверка типа данных
        if not isinstance(file_bytes, bytes):
            logging.error(f"❌ Ожидается bytes, получено: {type(file_bytes)}")
            raise TypeError("file_bytes должен быть bytes")

        logging.info(f"📦 Размер файла для загрузки: {len(file_bytes)} байт")

        # Метаданные
        file_metadata = {
            'name': filename,
            'description': description[:100],
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]

        # 🔥 Создаём BytesIO объект ПРАВИЛЬНО
        file_stream = io.BytesIO(file_bytes)

        # 🔥 MediaIoBaseUpload с правильными параметрами
        media = MediaIoBaseUpload(
            file_stream,
            mimetype='video/mp4',
            resumable=True,
            chunksize=256 * 1024  # 256KB chunks (стабильнее для Railway)
        )

        # Создание файла
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink, name'
        ).execute()

        # Делаем файл публичным по ссылке
        service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
            fields='id'
        ).execute()

        # Получаем финальную ссылку
        file = service.files().get(
            fileId=file['id'],
            fields='id, webViewLink, webContentLink, name'
        ).execute()

        logging.info(f"✅ Видео загружено: {file.get('webViewLink')}")

        return {
            'file_id': file['id'],
            'web_view_link': file.get('webViewLink'),
            'web_content_link': file.get('webContentLink'),
            'name': file.get('name')
        }

    except Exception as e:
        logging.error(f"❌ Ошибка Google Drive: {type(e).__name__}: {e}")
        raise