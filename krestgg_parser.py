# krestgg_parser.py
import re
import time
import logging
from typing import Dict, List
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_URL = "https://krestgg.ru"
SERVERS_TO_CHECK = [
    {"id": "AAS", "text_pattern": r"\[RU\]\[AAS"},
    {"id": "INV", "text_pattern": r"\[RU\]\[INV"},
    {"id": "MINI", "text_pattern": r"\[RU\]\[MINI"},
    {"id": "RAAS", "text_pattern": r"\[RU\]\[RAAS"},
    {"id": "TRN", "text_pattern": r"\[RU\]\[TRN"},
]

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--disable-gpu", "--single-process", "--disable-extensions", "--no-zygote"
]


class KrestGGParser:
    def __init__(self, timeout: int = 15000):
        self.timeout = timeout
        self._cache = {"data": {}, "timestamp": 0, "ttl": 120}

    async def get_pet_online_by_server(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        now = time.time()
        if not force_refresh and self._cache["data"] and (now - self._cache["timestamp"]) < self._cache["ttl"]:
            return self._cache["data"]

        logger.info("🔍 Сканирую сервера...")
        result = {}

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1440, "height": 900}
                )
                page = await context.new_page()

                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                await page.wait_for_load_state("networkidle", timeout=10000)
                await page.wait_for_timeout(2000)

                for srv in SERVERS_TO_CHECK:
                    try:
                        btn = page.get_by_text(re.compile(srv["text_pattern"])).first

                        if await btn.count() > 0:
                            raw_name = await btn.text_content()
                            clean_name = re.sub(r'\s*\d+/\d+.*', '', raw_name).strip()

                            logger.info(f"🔄 Переключаю на: {clean_name}")
                            await btn.click(force=True)
                            await page.wait_for_timeout(1500)

                            players = await self._extract_pet_players(page)
                            if players:
                                result[clean_name] = players
                                logger.debug(f"✅ {clean_name}: {len(players)} чел.")
                        else:
                            logger.debug(f"⚠️ Кнопка {srv['id']} не найдена")

                    except Exception as e:
                        logger.error(f"❌ Ошибка с сервером {srv['id']}: {e}")
                        continue

                self._cache["data"] = result
                self._cache["timestamp"] = time.time()
                return result

            except Exception as e:
                logger.error(f"❌ Глобальная ошибка парсинга: {e}")
                return {}
            finally:
                try:
                    await browser.close()
                except:
                    pass

    async def _extract_pet_players(self, page) -> List[str]:
        """Парсит ники с тегом [PET] или |PET| через Playwright локаторы"""
        players = set()
        try:
            # 🔧 ПОДДЕРЖКА ОБОИХ ФОРМАТОВ: [PET...] и |PET...|
            tag_pattern = re.compile(r"(?:\[PET[sStTpP]?\]|\|PET[sStTpP]?\|)", re.IGNORECASE)

            elements = await page.get_by_text(tag_pattern).all()

            for el in elements:
                try:
                    text = await el.text_content()
                    if not text: continue

                    # 🔧 Извлекаем имя после [PET] или |PET|
                    match = re.search(
                        r"(?:\[PET[sStTpP]?\]|\|PET[sStTpP]?\|)\s*(.+?)(?:В\s*друзья|$)",
                        text,
                        re.IGNORECASE | re.DOTALL
                    )
                    if match:
                        nick = match.group(1).strip()
                        nick = re.sub(r'<[^>]+>', '', nick).strip()

                        if 3 <= len(nick) <= 25:
                            players.add(nick)
                except:
                    continue
        except Exception as e:
            logger.debug(f"Ошибка парсинга игроков: {e}")

        return list(players)


parser = KrestGGParser()