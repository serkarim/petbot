# krestgg_parser.py
import re
import time
import logging
from typing import Dict, List
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://krestgg.ru"
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

        logger.info("🔍 Сканирую вкладки серверов...")
        result = {}

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    viewport={"width": 1440, "height": 900}
                )
                page = await context.new_page()

                # Переход и ожидание
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeout:
                    logger.debug("⏳ networkidle таймаут, продолжаем...")

                await page.wait_for_timeout(2500)  # Ждем рендер React

                server_tabs = await self._find_server_tabs(page)
                if not server_tabs:
                    logger.warning("⚠️ Вкладки серверов не найдены")
                    await browser.close()
                    return {}

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                for i, tab in enumerate(server_tabs, 1):
                    try:
                        raw_name = await tab.inner_text()
                        # Чистим название от онлайна
                        clean_name = re.sub(r'\s*\d+\s*/\s*\d+\(?\+?\d*\)?', '', raw_name).strip()

                        logger.debug(f"[{i}/{len(server_tabs)}] Кликаю на: {clean_name}")

                        # Клик с force=True (игнорирует перекрытия)
                        await tab.click(force=True)

                        # Ждем подгрузки данных сервера
                        await page.wait_for_load_state("networkidle", timeout=5000)
                        await page.wait_for_timeout(1000)

                        players = await self._extract_pet_players(page)
                        if players:
                            result[clean_name] = players
                            logger.debug(f"✅ {clean_name}: +{len(players)} игроков")

                        await page.wait_for_timeout(300)
                    except Exception as e:
                        logger.debug(f"⚠️ Ошибка вкладки #{i}: {e}")
                        continue

                await browser.close()
                self._cache["data"] = result
                self._cache["timestamp"] = time.time()
                return result

            except Exception as e:
                logger.error(f"❌ Ошибка парсинга: {type(e).__name__}: {e}")
                return {}
            finally:
                try:
                    await browser.close()
                except:
                    pass

    async def _find_server_tabs(self, page) -> List:
        """Ищет вкладки серверов в шапке по координатам и тексту"""
        # Паттерн: [RU][AAS+] Кресты
        pattern = re.compile(r"\[RU\]\[[\w+]+\]\s*Кресты")

        # 1. Ждем появления хотя бы одного элемента с текстом [RU]
        try:
            await page.wait_for_selector("text=[RU]", timeout=8000)
        except PlaywrightTimeout:
            logger.warning("⏳ Timeout ожидания [RU] элементов")
            return []

        # 2. Ищем ВСЕ элементы, содержащие текст сервера
        # locator("*").filter(has_text=...) находит родителя, содержащего текст
        candidates = await page.locator("*").filter(has_text=pattern).all()

        logger.debug(f"🔍 Найдено кандидатов с текстом сервера: {len(candidates)}")

        valid_tabs = []
        seen_y = set()

        for el in candidates:
            try:
                box = await el.bounding_box()
                if not box:
                    continue

                # ФИЛЬТР: Оставляем только элементы из верхней панели (меню)
                # Обычно меню находится в самом верху (Y < 150)
                if box['y'] > 150:
                    continue

                # ФИЛЬТР: Минимальный размер кнопки
                if box['width'] < 40 or box['height'] < 15:
                    continue

                # ДЕДУПЛИКАЦИЯ: Берем только один элемент из каждой строки (по Y)
                y_key = round(box['y'] / 10) * 10
                if y_key not in seen_y:
                    seen_y.add(y_key)
                    valid_tabs.append((box['x'], el))

            except Exception:
                continue

        # Сортировка слева направо (по X)
        valid_tabs.sort(key=lambda item: item[0])
        return [el for _, el in valid_tabs]

    async def _extract_pet_players(self, page) -> List[str]:
        """Парсинг ников [PET] из DOM"""
        js_code = """
        () => {
            const results = new Set();
            const tagRegex = /\\[PET[sStTpP]?\\]/i;
            const nameRegex = /(\\[PET[sStTpP]?\\]\\s*[A-Za-z0-9А-Яа-я_\\-\\.!?]{2,20})/i;

            // Ищем в основном контенте
            const mainArea = document.querySelector('main') || 
                             document.querySelector('section') || 
                             document.body;

            const walker = document.createTreeWalker(mainArea, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (!text || text.length > 60) continue;

                if (tagRegex.test(text)) {
                    const match = text.match(nameRegex);
                    if (match) {
                        let nick = match[1].trim();
                        // Чистим кнопку "В друзья"
                        nick = nick.replace(/В\\s*друзья/gi, '').trim();
                        if (nick.length >= 5 && nick.length <= 25 && !results.has(nick)) {
                            results.add(nick);
                        }
                    }
                }
            }
            return Array.from(results);
        }
        """
        try:
            nicks = await page.evaluate(js_code)
            return [str(n).strip() for n in nicks if n]
        except Exception as e:
            logger.debug(f"⚠️ Ошибка JS: {e}")
            return []


# Глобальный экземпляр
parser = KrestGGParser()