# krestgg_parser.py
import asyncio
import logging
import time
import re
from typing import List, Set
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://krestgg.ru"
CLAN_TAG = "PET"

# 🎯 ТОЧНЫЕ СЕЛЕКТОРЫ на основе твоего HTML
SELECTORS = {
    # Кнопки серверов (те что в шапке с онлайном)
    "server_buttons": "button.server-button, .server-card button, [data-server], .servers-list button",

    # Контейнер со списком игроков
    "players_container": ".players-list, .squad-list, .server-players, #players-container",

    # Отряды (squads)
    "squad_sections": ".squad, .squad-section, [class*='squad']",

    # Строка игрока (может быть div, span или просто текст после img)
    "player_row": ".player, .player-item, .squad-member",

    # Ник игрока - ИЩЕМ ТЕКСТ ПОСЛЕ КАРТИНКИ
    "nickname": "img + span, img + a, .player-name, .player-nick",
}

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
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
        """Сканирует все сервера и находит [PET]"""
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
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()

                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                await page.wait_for_timeout(1500)

                # Находим кнопки серверов
                server_buttons = await page.query_selector_all(SELECTORS["server_buttons"])

                if not server_buttons:
                    logger.warning("⚠️ Не найдены кнопки серверов!")
                    await browser.close()
                    return []

                logger.info(f"🎮 Найдено {len(server_buttons)} серверов")

                for i, button in enumerate(server_buttons, 1):
                    try:
                        server_name = await page.evaluate('el => el.textContent.trim()', button)
                        logger.debug(f"[{i}/{len(server_buttons)}] Кликаем: {server_name}")

                        await button.click()
                        await page.wait_for_timeout(1000)

                        # Парсим всех игроков на странице
                        pet_players = await self._extract_pet_nicks(page)

                        if pet_players:
                            logger.debug(f"✅ {server_name}: найдено {len(pet_players)} [PET]")
                            all_online.update(pet_players)

                        await page.wait_for_timeout(200)

                    except Exception as e:
                        logger.debug(f"⚠️ Ошибка сервера #{i}: {e}")
                        continue

                await browser.close()

                result = sorted(list(all_online))
                self._cache["data"] = result
                self._cache["timestamp"] = time.time()

                logger.info(f"✨ Всего [{self.clan_tag}] онлайн: {len(result)}")
                return result

            except Exception as e:
                logger.error(f"❌ Ошибка: {type(e).__name__}: {e}")
                return []

    async def _extract_pet_nicks(self, page) -> List[str]:
        """Извлекает ники с [PET] используя JS"""
        js_code = f"""
        () => {{
            const results = [];
            const tag = "{self.clan_tag}".toUpperCase();
            const tagPattern = `[${{tag}}]`;

            // Ищем ВСЕ текстовые узлы на странице
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );

            const textNodes = [];
            while (walker.nextNode()) {{
                textNodes.push(walker.currentNode);
            }}

            // Ищем ники с тегом [PET]
            for (const node of textNodes) {{
                const text = node.textContent.trim();
                if (!text) continue;

                // Разбиваем на слова/ники
                const words = text.split(/\\s+/);
                for (const word of words) {{
                    const cleanWord = word.replace(/[^\\w\\[\\]]/g, '');
                    if (cleanWord.toUpperCase().includes(tagPattern)) {{
                        // Убираем "Вдрузья" и другой мусор
                        const nick = cleanWord.replace(/Вдрузья/g, '').trim();
                        if (nick && nick.length >= 3 && !results.includes(nick)) {{
                            results.push(nick);
                        }}
                    }}
                }}

                // Также проверяем весь текст целиком
                if (text.toUpperCase().includes(tagPattern)) {{
                    const cleanText = text.replace(/Вдрузья/g, '').trim();
                    const words2 = cleanText.split(/\\s+/);
                    for (const w of words2) {{
                        if (w.toUpperCase().includes(tagPattern) && !results.includes(w)) {{
                            results.push(w);
                        }}
                    }}
                }}
            }}

            // Дополнительно ищем по элементам после картинок
            const imgs = document.querySelectorAll('img');
            for (const img of imgs) {{
                let next = img.nextElementSibling;
                if (next) {{
                    const text = next.textContent.trim();
                    if (text.toUpperCase().includes(tagPattern)) {{
                        const clean = text.replace(/Вдрузья/g, '').trim();
                        if (clean && !results.includes(clean)) {{
                            results.push(clean);
                        }}
                    }}
                }}
            }}

            return results;
        }}
        """
        try:
            nicks = await page.evaluate(js_code)
            return [str(n).strip() for n in nicks if n and str(n).strip()]
        except Exception as e:
            logger.debug(f"⚠️ Ошибка JS: {e}")
            return []


parser = KrestGGParser()