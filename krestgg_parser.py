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

                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeout:
                    logger.debug("⏳ networkidle таймаут, продолжаем...")

                await page.wait_for_timeout(2500)

                server_tabs = await self._find_server_tabs(page)
                if not server_tabs:
                    logger.warning("⚠️ Вкладки серверов не найдены")
                    await browser.close()
                    return {}

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                for i, tab in enumerate(server_tabs, 1):
                    try:
                        raw_name = await tab.inner_text()
                        clean_name = re.sub(r'\s*\d+\s*/\s*\d+\s*\(?\+?\d*\)?', '', raw_name).strip()

                        logger.debug(f"[{i}/{len(server_tabs)}] Кликаю на: {clean_name}")
                        await tab.click(force=True)

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
        # 🔧 ИСПРАВЛЕНО: корректный паттерн для [RU][AAS+] Кресты
        pattern = re.compile(r"\[RU\]\[[A-Z0-9+]+\]\s*Кресты", re.IGNORECASE)

        try:
            await page.wait_for_selector("text=[RU]", timeout=8000)
        except PlaywrightTimeout:
            logger.warning("⏳ Timeout ожидания [RU] элементов")
            return []

        candidates = await page.locator("*").filter(has_text=pattern).all()
        logger.debug(f"🔍 Найдено кандидатов с текстом сервера: {len(candidates)}")

        valid_tabs = []
        seen_y = set()

        for el in candidates:
            try:
                box = await el.bounding_box()
                if not box:
                    continue

                # 🔧 ИСПРАВЛЕНО: более мягкий фильтр по Y (было >150, стало >200)
                if box['y'] > 200:
                    continue

                if box['width'] < 40 or box['height'] < 15:
                    continue

                y_key = round(box['y'] / 10) * 10
                if y_key not in seen_y:
                    seen_y.add(y_key)
                    valid_tabs.append((box['x'], el))

            except Exception:
                continue

        valid_tabs.sort(key=lambda item: item[0])
        return [el for _, el in valid_tabs]

    async def _extract_pet_players(self, page) -> List[str]:
        """Парсинг ников [PET] из DOM"""
        # 🔧 ИСПРАВЛЕНО: корректные регулярки для тегов клана
        js_code = """
        () => {
            const results = new Set();
            // 🔧 Правильный паттерн: ищем [PET], [PETt], [PETs]
            const tagPattern = /\\[(PET|PETt|PETs)\\]/i;
            // Паттерн для ника после тега
            const namePattern = /[A-Za-z0-9А-Яа-я_\\-.!?]{2,25}/;

            // 🔧 Ищем по ВСЕМУ body, а не только main/section
            const walker = document.createTreeWalker(
                document.body, 
                NodeFilter.SHOW_TEXT, 
                null, 
                false
            );

            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (!text || text.length > 80) continue;

                // Проверяем наличие тега клана
                if (tagPattern.test(text)) {
                    // Извлекаем ник после тега
                    const match = text.match(new RegExp(
                        String.raw`\\[(?:PET|PETt|PETs)\\]\\s*` + namePattern.source, 
                        'i'
                    ));
                    if (match) {
                        let nick = `[${match[0].match(tagPattern)[0]}] ${match[1]}`.trim();
                        // Чистим "В друзья" и лишние пробелы
                        nick = nick.replace(/\\s*В\\s*друзья\\s*/gi, '').trim();

                        // Фильтр: ник от 5 до 30 символов
                        if (nick.length >= 6 && nick.length <= 35 && !results.has(nick)) {
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
            return [str(n).strip() for n in nicks if n and isinstance(n, str)]
        except Exception as e:
            logger.debug(f"⚠️ Ошибка JS: {e}")
            return []


# Глобальный экземпляр
parser = KrestGGParser()