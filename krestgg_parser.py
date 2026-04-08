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
        self._cache = {"data": {}, "timestamp": 0, "ttl": 120}  # Кэш 2 минуты

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
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1440, "height": 900}
                )
                page = await context.new_page()

                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                # Ждём полной загрузки сети и рендера JS-компонентов
                await page.wait_for_load_state("networkidle", timeout=10000)
                await page.wait_for_timeout(1500)

                server_tabs = await self._find_server_tabs(page)
                if not server_tabs:
                    logger.warning("⚠️ Вкладки серверов не найдены. Проверяю URL: %s", page.url)
                    await browser.close()
                    return {}

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                for tab in server_tabs:
                    try:
                        raw_name = await tab.inner_text()
                        # Чистим название от онлайна: "100 /100 (+14)" -> "[AAS+] Кресты"
                        clean_name = re.sub(r'\s*\d+\s*/\s*\d+\(?\+?\d*\)?', '', raw_name).strip()

                        logger.debug(f"🔄 Переключаю на: {clean_name}")
                        await tab.click()

                        # Ждём подгрузки списка игроков после клика
                        await page.wait_for_load_state("networkidle", timeout=5000)
                        await page.wait_for_timeout(400)

                        players = await self._extract_pet_players(page)
                        if players:
                            result[clean_name] = players
                            logger.debug(f"✅ {clean_name}: +{len(players)} игроков")

                        await page.wait_for_timeout(200)
                    except Exception as e:
                        logger.debug(f"⚠️ Ошибка вкладки {raw_name}: {e}")
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
        """Находит кликабельные вкладки серверов по маркеру [RU]"""
        logger.info("⏳ Ожидаю рендер вкладок...")
        # 1. Ждём появления хотя бы одного элемента с [RU]
        try:
            await page.locator("text=[RU]").first.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            logger.warning("⏳ Timeout ожидания вкладок, пробую парсить как есть...")

        # 2. Собираем ВСЕ элементы, содержащие [RU] (Playwright сам склеивает разбитые <span>)
        candidates = await page.locator("text=[RU]").all()
        logger.debug(f"🔎 Найдено кандидатов с [RU]: {len(candidates)}")

        valid_tabs = []
        seen_rows = set()

        for el in candidates:
            try:
                box = await el.bounding_box()
                if not box: continue

                # Отсеиваем мелкие текстовые ноды внутри кнопок (ширина/высота слишком маленькие)
                if box.get('width', 0) < 35 or box.get('height', 0) < 15:
                    continue

                # Группируем по строке (Y координата с шагом 10px)
                row_key = round(box["y"] / 10) * 10
                if row_key not in seen_rows:
                    seen_rows.add(row_key)
                    valid_tabs.append((box["x"], el))
            except Exception:
                continue

        # Сортируем слева направо, как на экране
        valid_tabs.sort(key=lambda item: item[0])
        return [el for _, el in valid_tabs]

    async def _extract_pet_players(self, page) -> List[str]:
        """Извлекает ники с тегом [PET] и его вариациями"""
        js_code = """
        () => {
            const results = new Set();
            const tagRegex = /\\[PET[sStTpP]?\\]/i;
            const nameRegex = /(\\[PET[sStTpP]?\\]\\s*[A-Za-z0-9А-Яа-я_\\-\\.!?]{2,20})/i;

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
            logger.debug(f"⚠️ Ошибка JS-извлечения: {e}")
            return []


# Глобальный экземпляр
parser = KrestGGParser()