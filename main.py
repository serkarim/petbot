# main.py
import os
import asyncio
import logging
import threading
from aiogram.utils.executor import start_polling
import uvicorn

# Импортируем бота и диспетчер из bot.py
from bot import bot, dp, on_startup, on_shutdown

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_bot():
    """Запускает бота в отдельном потоке с собственным event loop"""
    logger.info("🤖 Запуск бота в потоке...")

    # Создаём новый event loop для этого потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Запускаем polling в этом loop
        loop.run_until_complete(
            start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
    finally:
        loop.close()


async def run_api():
    """Запускает FastAPI сервер"""
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🌐 Запуск API на порту {port}...")

    # Импортируем здесь, чтобы избежать циклических импортов
    from backend.app import app as fastapi_app

    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    await server.serve()


def main():
    """Точка входа"""
    logger.info("🚀 Запуск PET Bot + Mini App...")

    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Запускаем API в главном потоке (для Railway)
    try:
        asyncio.run(run_api())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")


if __name__ == "__main__":
    main()