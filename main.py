# main.py
import os
import asyncio
import logging
from aiogram.utils.executor import start_polling
import uvicorn

# Импортируем бота и диспетчер из bot.py
from bot import dp, on_startup, on_shutdown, bot

# Импортируем FastAPI приложение
from backend.app import app as fastapi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_bot():
    """Запускает Telegram бота"""
    logger.info("🤖 Запуск бота...")
    try:
        await start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")


async def run_api():
    """Запускает FastAPI сервер для Mini App"""
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🌐 Запуск API на порту {port}...")
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Запускает оба процесса параллельно"""
    logger.info("🚀 Запуск PET Bot + Mini App...")

    # Создаём задачи
    bot_task = asyncio.create_task(run_bot())
    api_task = asyncio.create_task(run_api())

    # Ждём завершения любой из задач (если одна упадёт — перезапустим)
    done, pending = await asyncio.wait(
        [bot_task, api_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # Отменяем оставшиеся задачи
    for task in pending:
        task.cancel()

    logger.warning("⚠️ Один из процессов завершён")


if __name__ == "__main__":
    asyncio.run(main())