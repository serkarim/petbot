# krestgg_parser.py
import re
import time
import logging
from typing import Dict, List
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://krestgg.ru"
# Аргументы для запуска Chromium на Railway (экономия памяти и обход блокировок)
BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--disable-gpu", "--single-process", "--disable-extensions", "--no-zygote"
]


class KrestGGParser:
    def __init__(self, timeout: int = 15000):
        self.timeout = timeout
        self._cache = {"data": {}, "timestamp": 0, "ttl": 120}  # Кэш на 2 минуты

    async def get_pet_online_by_server(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        """Возвращает словарь {название_сервера: [список_игроков]}"""
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
                await page.wait_for_load_state("networkidle", timeout=8000)
                await page.wait_for_timeout(1000)  # Пауза для прогрузки React-компонентов

                # 1. Находим вкладки серверов
                server_tabs = await self._find_server_tabs(page)
                if not server_tabs:
                    logger.warning("⚠️ Вкладки серверов не найдены")
                    return {}

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                # 2. Кликаем по каждой вкладке и парсим
                for tab in server_tabs:
                    try:
                        raw_name = await tab.inner_text()
                        # Чистим название от цифр онлайна: "100/100(+14)" -> "[AAS+] Кресты"
                        clean_name = re.sub(r'\s*\d+\s*/\s*\d+\(?\+?\d*\)?', '', raw_name).strip()

                        logger.debug(f"🔄 Переключаю на: {clean_name}")
                        await tab.click()

                        # Ждём обновления списка игроков (лоадер или просто сеть)
                        await page.wait_for_load_state("networkidle", timeout=5000)
                        await page.wait_for_timeout(400)

                        # Парсим игроков для этого сервера
                        players = await self._extract_pet_players(page)
                        if players:
                            result[clean_name] = players
                            logger.debug(f"✅ {clean_name}: +{len(players)} игроков")

                        await page.wait_for_timeout(200)  # Небольшая пауза между кликами
                    except Exception as e:
                        logger.debug(f"⚠️ Ошибка вкладки {raw_name}: {e}")
                        continue

                await browser.close()
                self._cache["data"] = result
                self._cache["timestamp"] = time.time()
                return result

            except Exception as e:
                logger.error(f"❌ Ошибка парсинга: {e}")
                return {}
            finally:
                try:
                    await browser.close()
                except:
                    pass

    async def _find_server_tabs(self, page) -> List:
        """Находит кликабельные вкладки серверов, игнорируя скрытые элементы"""
        # Паттерн: [RU][СЕРВЕР] Кресты. Учитываем +, цифры и буквы
        pattern = re.compile(r"\[RU\]\[[\w+]+\]\s*Кресты")

        candidates = await page.locator("div, button, span, a").filter(has_text=pattern).all()

        tabs_with_coords = []
        seen_y = set()

        for el in candidates:
            try:
                # is_interactive() и bounding_box() — асинхронные методы
                if not await el.is_interactive():
                    continue

                box = await el.bounding_box()
                if not box:
                    continue

                # Фильтр по минимальному размеру, чтобы не брать текстовые ноды внутри кнопок
                if box['height'] < 20 or box['width'] < 50:
                    continue

                # Привязываемся к Y-координате (строка), чтобы исключить дубли
                y_key = round(box["y"])
                if y_key not in seen_y:
                    seen_y.add(y_key)
                    # Сохраняем X координату вместе с элементом
                    tabs_with_coords.append((box["x"], el))
            except Exception:
                continue

        # Сортируем уже полученные данные по X координате (слева направо)
        tabs_with_coords.sort(key=lambda item: item[0])

        # Возвращаем только элементы
        return [el for _, el in tabs_with_coords]

    async def _extract_pet_players(self, page) -> List[str]:
        """Извлекает ники с тегом [PET] и его вариациями (PETS, PETt, PETP и т.д.)"""
        js_code = """
        () => {
            const results = new Set();
            // Ловит [PET] + опционально s/S/t/T/p/P в конце, любой регистр
            const tagRegex = /\\[PET[sStTpP]?\\]/i;
            const nameRegex = /(\\[PET[sStTpP]?\\]\\s*[A-Za-z0-9А-Яа-я_\\-\\.!?]{2,20})/i;

            // Ищем только в основном контенте (main/section), пропускаем шапку сайта
            const mainArea = document.querySelector('main') || 
                             document.querySelector('section') || 
                             document.body;

            const walker = document.createTreeWalker(mainArea, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (!text || text.length > 60) continue;

                // Проверяем наличие тега в тексте
                if (tagRegex.test(text)) {
                    const match = text.match(nameRegex);
                    if (match) {
                        let nick = match[1].trim();
                        // Чистим прилипшую кнопку "В друзья"
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


# Глобальный экземпляр для импорта
parser = KrestGGParser()