# krestgg_parser.py
import asyncio
import logging
import re
import time
from typing import List, Set
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_URL = "https://krestgg.ru"
CLAN_TAG = "PET"

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-s",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process",
    "--disable-extensions",
    "--no-zygote",
]


class KrestGGParser:
    def __init__(self, clan_tag: str = CLAN_TAG, timeout: int = 15000):
        self.clan_tag = clan_tag.upper()
        self.timeout = timeout
        self._cache = {"data": [], "timestamp": 0, "ttl": 120}

    async def get_pet_online(self, force_refresh: bool = False) -> List[str]:
        now = time.time()
        if not force_refresh and self._cache["data"] and (now - self._cache["timestamp"]) < self._cache["ttl"]:
            return self._cache["data"]

        logger.info(f"🔍 Сканирую krestgg.ru на наличие [{self.clan_tag}]...")
        all_online: Set[str] = set()

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1440, "height": 900}
                )
                page = await context.new_page()
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                await page.wait_for_timeout(1500)  # Ждём инициализацию SPA

                # Ищем вкладки серверов по тексту [RU]
                server_tabs = await page.locator("*").filter(has_text=re.compile(r"\[RU\]")).all()
                if not server_tabs:
                    logger.warning("⚠️ Не найдены вкладки серверов")
                    await browser.close()
                    return []

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                for i, tab in enumerate(server_tabs, 1):
                    try:
                        tab_text = await tab.inner_text()
                        # Пропускаем дубли и не-серверные элементы
                        if "Кресты" not in tab_text:
                            continue

                        logger.debug(f"[{i}/{len(server_tabs)}] Переключаю: {tab_text.strip()}")
                        await tab.click()

                        # Ждём обновления списка игроков (лоадер или просто сеть)
                        await page.wait_for_load_state("networkidle", timeout=5000)
                        await page.wait_for_timeout(400)

                        nicks = await self._extract_pet_nicks(page)
                        if nicks:
                            logger.debug(f"✅ {tab_text.strip()}: +{len(nicks)} игроков")
                            all_online.update(nicks)

                    except Exception as e:
                        logger.debug(f"⚠️ Ошибка на вкладке #{i}: {e}")
                        continue

                await browser.close()
                result = sorted(list(all_online))
                self._cache["data"] = result
                self._cache["timestamp"] = time.time()
                logger.info(f"✨ Всего [{self.clan_tag}] онлайн: {len(result)}")
                return result

            except Exception as e:
                logger.error(f"❌ Ошибка парсинга: {type(e).__name__}: {e}")
                return []

    async def _extract_pet_nicks(self, page) -> List[str]:
        """Ищет ники с [PET] или [PETs] через нативные локаторы Playwright"""
        nicks = set()
        # Регулярка для тега клана
        tag_pattern = re.compile(r"\[PETs?\]", re.IGNORECASE)

        # Ищем только видимые элементы, содержащие тег
        elements = await page.locator("*").filter(has_text=tag_pattern).all()

        for el in elements:
            try:
                text = await el.inner_text()
                if not text or len(text) > 100:  # Игнорируем огромные блоки
                    continue

                # 1. Убираем кнопку "В друзья" (часто прилипает без пробела)
                clean = re.sub(r"В\s*друзья", "", text, flags=re.IGNORECASE)
                # 2. Схлопываем пробелы и переносы строк
                clean = re.sub(r"\s+", " ", clean).strip()
                # 3. Вытаскиваем ник: [PET] Name или [PETs] Name
                match = re.search(r"(\[PETs?\]\s*[A-Za-z0-9А-Яа-я_\-\.\!\?]+)", clean, re.IGNORECASE)

                if match:
                    nick = match.group(1).strip()
                    if 5 <= len(nick) <= 30:  # Фильтр адекватной длины
                        nicks.add(nick)
            except Exception:
                continue

        return list(nicks)


parser = KrestGGParser()