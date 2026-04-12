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
                # Ждем полной загрузки сети и рендера JS-компонентов
                await page.wait_for_load_state("networkidle", timeout=10000)
                await page.wait_for_timeout(2000)  # Доп. пауза для React-рендера

                server_tabs = await self._find_server_tabs(page)
                if not server_tabs:
                    logger.warning("⚠️ Вкладки серверов не найдены")
                    await browser.close()
                    return {}

                logger.info(f"🎮 Найдено {len(server_tabs)} серверов")

                for i, tab in enumerate(server_tabs, 1):
                    try:
                        raw_name = await tab.inner_text()
                        # Чистим название от онлайна: "100 /100 (+14)" -> "[AAS+] Кресты"
                        clean_name = re.sub(r'\s*\d+\s*/\s*\d+\(?\+?\d*\)?', '', raw_name).strip()

                        logger.debug(f"[{i}/{len(server_tabs)}] Переключаю на: {clean_name}")

                        # 1. Кликаем по вкладке
                        await tab.click(force=True)

                        # 2. Ждём завершения AJAX-запроса
                        try:
                            await page.wait_for_load_state("networkidle", timeout=6000)
                        except PlaywrightTimeout:
                            pass

                        # 3. Ждём рендера DOM (SPA часто задерживается)
                        await page.wait_for_timeout(1000)

                        # 4. Парсим игроков
                        players = await self._extract_pet_players(page)
                        if players:
                            result[clean_name] = players
                            logger.debug(f"✅ {clean_name}: +{len(players)} игроков")
                        else:
                            logger.debug(f"⚪ {clean_name}: пусто или не загрузилось")

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
        """Находит кликабельные вкладки серверов в шапке"""
        # Паттерн ищет текст [RU][...] Кресты
        pattern = re.compile(r"\[RU\]\[[\w+]+\]\s*Кресты")

        # Ищем только в интерактивных элементах
        candidates = await page.locator("div, button, span, a").filter(has_text=pattern).all()

        valid_tabs = []
        seen_texts = set()

        for el in candidates:
            try:
                box = await el.bounding_box()
                if not box or box.get('y', 999) > 150:  # Фильтр по высоте (верхняя панель)
                    continue

                text = await el.inner_text()
                clean = re.sub(r'\s*\d+\s*/\s*\d+\(?\+?\d*\)?', '', text).strip()

                # Точное совпадение с паттерном сервера
                if not re.fullmatch(r"\[RU\]\[[\w+]+\]\s*Кресты", clean):
                    continue

                # Дедупликация по тексту (чтобы не парсить один сервер дважды)
                if clean in seen_texts:
                    continue
                seen_texts.add(clean)

                valid_tabs.append((box['x'], el, clean))
            except Exception:
                continue

        # Сортируем слева направо
        valid_tabs.sort(key=lambda x: x[0])
        return [(el, txt) for _, el, txt in valid_tabs[:6]]

    async def _extract_pet_players(self, page) -> List[str]:
        """Ищет ники с тегом [PET...] или |PET...|"""
        js_code = """
        () => {
            const results = new Set();
            // ✅ ОБНОВЛЕНО: Ищет и [PET], и |PET|
            const tagRegex = /(\[PET[sStTpP]?\]|\|PET[sStTpP]?\|)/i;
            // ✅ ОБНОВЛЕНО: Захватывает тег и следующее за ним имя
            const nameRegex = /((?:\[PET[sStTpP]?\]|\|PET[sStTpP]?\|)\s*[A-Za-z0-9А-Яа-я_\-\.!?]{2,20})/i;

            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (!text || text.length > 60) continue;

                if (tagRegex.test(text)) {
                    const match = text.match(nameRegex);
                    if (match) {
                        let nick = match[1].trim();
                        // Чистим прилипшую кнопку "В друзья"
                        nick = nick.replace(/В\s*друзья/gi, '').trim();
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