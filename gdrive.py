# gdrive.py
import os
import io
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_drive_service():
    """Инициализация сервиса Google Drive из ENV"""
    creds_json = os.getenv('GDRIVE_CREDENTIALS')
    if not creds_json:
        raise Exception("❌ Не найдена переменная GDRIVE_CREDENTIALS")

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(creds_json), scopes=SCOPES)

    return build('drive', 'v3', credentials=credentials)


def upload_video_to_drive(file_bytes: bytes, filename: str, description: str = "") -> dict:
    """Загружает видео на Google Drive"""
    try:
        service = get_drive_service()
        folder_id = os.getenv('GDRIVE_FOLDER_ID')

        # Метаданные
        file_metadata = {'name': filename, 'description': description[:100]}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        # Загрузка
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype='video/mp4',
            resumable=True,
            chunksize=1024 * 1024
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        # Делаем файл публичным (доступ по ссылке)
        service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        # Получаем ссылку
        file = service.files().get(fileId=file['id'], fields='webViewLink').execute()

        logging.info(f"✅ Загружено на диск: {file.get('webViewLink')}")

        return {
            'file_id': file['id'],
            'web_view_link': file.get('webViewLink')
        }

    except Exception as e:
        logging.error(f"❌ Ошибка Google Drive: {e}")
        raise