import hashlib
import json
import os
import asyncio
import logging
import time
from pathlib import Path
from pprint import pprint
import random
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from bot_instance import bot
import psutil
from playwright.async_api import async_playwright, Page, ElementHandle
from typing import Tuple, List, Dict, Any
from api import openai_api
from config import (
    COOKIES_PATH,
    AIRBNB_MESSAGES_PATH,
    CHAT_CONTEXT_PATH,
    UNREAD_MESSAGES_PATH,
)
from airbnb_service import state

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ADMIN_IDS = list(map(int, os.getenv("ADMINS", "").split(',')))
AIRBNB_URL = "https://www.airbnb.com/hosting/messages/"
logger = logging.getLogger(__name__)


class AutoStopError(Exception):
    """Автоматическая остановка по внутренней логике (например, вышли из аккаунта)."""
    pass


async def notify_admins(text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить сообщение админу {admin_id}: {e}")


async def prepare_browser(p):
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        timezone_id="Europe/Moscow",
        locale="en"
    )
    await load_cookies(context)
    page = await context.new_page()
    return context, page


async def load_cookies(context, path=COOKIES_PATH):
    import json

    logger.info("🔄 Загрузка cookies из файла...")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise AutoStopError("🔐 Аккаунт не авторизован: файл cookies.json пустой.")

            cookies = json.loads(content)

        for cookie in cookies:
            if cookie.get("sameSite") not in ["Strict", "Lax", "None"]:
                cookie["sameSite"] = "Lax"
            for key in ["storeId", "hostOnly"]:
                cookie.pop(key, None)

        await context.add_cookies(cookies)
        logger.info(f"✅ Загружено {len(cookies)} cookies.")

    except AutoStopError:
        raise
    except Exception as e:
        logger.error(f"❌ Не удалось загрузить cookies: {e}")
        raise AutoStopError("🔐 Аккаунт не авторизован: авторизируйтесь снова.")


async def check_logged_in(page):
    logger.info("🔐 Проверка входа в аккаунт...")

    try:
        await page.goto("https://www.airbnb.com/account-settings", timeout=5000)
        await page.wait_for_load_state("networkidle")

        current_url = page.url
        logger.debug(f"🌐 Текущий URL: {current_url}")

        if "/login" in current_url:
            raise AutoStopError("🔐 Вход в аккаунт не подтвежден")

        # Пробуем найти div с классом _184uai1
        try:
            email_div = await page.query_selector("div._184uai1")
            if email_div:
                text_content = await email_div.text_content()
                logger.debug(f"📧 Найден блок профиля: {text_content}")
                if "@" in text_content:
                    logger.info("✅ Найден email в профиле — вход подтверждён.")
                    return True
        except Exception as e:
            logger.debug(f"⚠️ Не удалось извлечь email-блок: {e}")

        # Дополнительная проверка через input email
        try:
            await page.wait_for_selector("input[name='email']", timeout=1000)
            logger.info("✅ Найден input email — вход выполнен.")
            return True
        except:
            logger.debug("⏳ input[name='email'] не найден, проверим заголовок...")

        # Проверка заголовка страницы
        try:
            title_text = await page.title()
            logger.debug(f"📝 Заголовок страницы: {title_text}")
            if "Account" in title_text or "Настройки" in title_text:
                logger.info("✅ По заголовку страницы — вход выполнен.")
                return True
        except:
            logger.debug("⚠️ Не удалось получить заголовок.")

        raise AutoStopError("🔐 Вход в аккаунт не подтвежден")

    except Exception as e:
        raise AutoStopError("🔐 Вход в аккаунт не подтвежден")


async def get_message_data(page: Page) -> Tuple[int, List[Dict[str, str]]]:
    try:
        await page.goto("https://www.airbnb.com/hosting/messages/", timeout=20000)
        await page.wait_for_selector("div[data-listrow='true']", timeout=10000)
    except PlaywrightTimeoutError:
        logger.error("❌ Не удалось найти список сообщений — возможно, вышли из аккаунта.")
        # Поднимаем исключение, чтобы остановить работу
        raise AutoStopError("🔐 Выход из аккаунта Airbnb.")

    # сохраняем HTML
    html = await page.content()
    with open(AIRBNB_MESSAGES_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    unread_messages = []
    elements = await page.query_selector_all("div[data-listrow='true']")
    allowed_guests = {"artem", "артем", "nikolay", "николай"}

    for i, el in enumerate(elements):
        try:
            await page.wait_for_timeout(random.randint(100, 300))  # <– имитация реакции

            full_text = await el.inner_text()
            is_unread = "Unread" in full_text
            forced_unread = False

            participants_el = await el.query_selector("span.oj9ozqm")
            await page.wait_for_timeout(random.randint(50, 150))

            message_el = await el.query_selector("div.sx0gwsg span.oj9ozqm")
            date_el = await el.query_selector("div.t66yo6r")

            participants = await participants_el.inner_text() if participants_el else ""
            message_text = await message_el.inner_text() if message_el else ""
            date_text = await date_el.inner_text() if date_el else ""

            # 🔍 Фильтрация по допустимым именам
            participants_clean = participants.lower()
            if not any(name in participants_clean for name in allowed_guests):
                logger.info(f"🚫 [Chat #{i + 1}] Участники не соответствуют фильтру: {participants}")
                continue

            # Принудительная метка как непрочитанного, если последнее сообщение от гостя
            if i == 0 and not is_unread:
                aria_label = await el.get_attribute("aria-label")
                if aria_label and "sent" in aria_label:
                    sender = aria_label.split("sent")[0].lower()
                    if "you" not in sender and "host" not in sender:
                        forced_unread = True
                        logger.info(
                            "📌 Первый чат прочитан автоматически, но последнее сообщение от гостя — обрабатываем.")

            if is_unread or forced_unread:
                inner_div = await el.query_selector('div[id^="inbox_list_"]')
                if not inner_div:
                    continue
                raw_id = await inner_div.get_attribute("id")
                if not raw_id or not raw_id.startswith("inbox_list_"):
                    continue

                chat_id = raw_id.replace("inbox_list_", "")
                unread_messages.append({
                    "id": chat_id,
                    "index": i + 1,
                    "participants": participants,
                    "text": message_text,
                    "date": date_text
                })

        except Exception as e:
            logger.warning(f"⚠️ Ошибка при парсинге сообщения #{i + 1}: {e}")
            continue

    with open(UNREAD_MESSAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(unread_messages, f, ensure_ascii=False, indent=2)

    return len(unread_messages), unread_messages


async def parse_chat_details(page: Page, target_chat_id: str) -> Dict[str, Any] | None:
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        try:
            target_selector = f'div[id="inbox_list_{target_chat_id}"]'
            await page.wait_for_selector(target_selector, timeout=7000)
            chat_element = await page.query_selector(target_selector)

            if not chat_element:
                return None

            await chat_element.click()
            await page.wait_for_timeout(random.randint(2000, 4000))

            guest_name_el = await page.query_selector("div[class*='tv848kg']")
            await page.wait_for_timeout(random.randint(100, 200))

            guest_name = await guest_name_el.inner_text() if guest_name_el else "Имя не найдено"
            guest_name = guest_name.replace("About ", "").strip()

            # Сообщения
            raw_messages = []
            message_blocks = await page.query_selector_all("div[class*='fwqd6yv']")
            for msg in message_blocks[-10:]:
                await page.wait_for_timeout(random.randint(60, 200))
                text_el = await msg.query_selector("div.t12j2ntd")
                text = await text_el.inner_text() if text_el else ""
                if not text.strip():
                    continue

                sender = "Неизвестно"
                aria_label = await msg.get_attribute("aria-label")
                if aria_label:
                    sender_name = aria_label.split(" sent")[0].strip().lower()
                    guest_clean = guest_name.lower()
                    if guest_clean in sender_name or sender_name in guest_clean:
                        sender = f"{guest_name} | Гость"
                    else:
                        sender = "Хост"

                raw_messages.append({"sender": sender, "text": text.strip()})

            resolved_messages = [f"{m['sender']}: {m['text']}" for m in raw_messages]

            # Бронирование
            try:
                blocks = await page.query_selector_all("div.l2aukgi")
                if len(blocks) >= 3:
                    listing_name = await blocks[0].inner_text()
                    dates = await blocks[1].inner_text()
                    guests = await blocks[2].inner_text()
                    reservation_text = f"{listing_name} | {dates} | {guests}"
                else:
                    reservation_text = "Недостаточно данных"
            except:
                reservation_text = "Бронирование не найдено"

            # Инфо о госте
            try:
                guest_info_blocks = await page.query_selector_all("div.ht5ibok")
                guest_rating = await guest_info_blocks[0].inner_text() if len(guest_info_blocks) > 0 else "Нет рейтинга"
                verification = await guest_info_blocks[1].inner_text() if len(
                    guest_info_blocks) > 1 else "Нет верификации"
                joined = await guest_info_blocks[2].inner_text() if len(
                    guest_info_blocks) > 2 else "Дата регистрации неизвестна"

                additional_info = ""
                if len(guest_info_blocks) > 3:
                    parts = []
                    for block in guest_info_blocks[3:]:
                        try:
                            text = await block.inner_text()
                            if text.strip():
                                parts.append(text.strip())
                        except:
                            continue
                    if parts:
                        additional_info = " | " + " | ".join(parts)

                guest_info = f"{guest_name} | {guest_rating} | {verification} | {joined}{additional_info}"
            except:
                guest_info = "Нет данных"

            return {
                "id": target_chat_id,
                "last_messages": resolved_messages,
                "reservation": reservation_text,
                "guest_info": guest_info
            }

        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                return {
                    "id": target_chat_id,
                    "last_messages": [],
                    "reservation": "Ошибка",
                    "guest_info": "Ошибка"
                }
            await page.wait_for_timeout(2000)


async def send_message_to_unread(page: Page, chat_ids: List[str], message_text: str):
    for chat_id in chat_ids:
        try:
            url = f"https://www.airbnb.com/guest/messages/{chat_id}"
            logger.info(f"🌐 Переход к чату: {url}")

            response = await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            if not response or not response.ok:
                logger.error(f"❌ Страница {url} не загрузилась: status={response.status if response else 'None'}")
                raise Exception(f"Не удалось загрузить страницу Airbnb для чата {chat_id}")

            logger.info("✅ Страница загружена")
            await page.wait_for_timeout(5000)
            logger.debug(f"📍 Текущий URL: {page.url}")

            # 🔐 Проверка авторизации
            if "auth" in page.url or "login" in page.url:
                logger.error(f"🔒 Сессия сброшена при переходе к чату {chat_id}.")
                break

            # ⏳ Ожидание поля ввода
            textarea = await page.query_selector("textarea#message_input")
            if not textarea:
                logger.warning(f"❌ Не найдено поле ввода в чате {chat_id}")
                continue

            # 👆 Кликаем в поле
            box = await textarea.bounding_box()
            if box:
                await page.mouse.move(box["x"] + 5, box["y"] + 5)
                await page.mouse.click(box["x"] + 5, box["y"] + 5)
                await page.wait_for_timeout(300)

            # ⌨️ Ввод текста
            for char in message_text:
                await textarea.type(char)
                await page.wait_for_timeout(70)

            # 🔐 Повторная проверка авторизации
            if "auth" in page.url or "login" in page.url:
                logger.error(f"🔒 Сессия сброшена перед отправкой в чате {chat_id}.")
                break

            # 📨 Кнопка отправки
            send_button = await page.query_selector("button[data-testid='messaging_compose_bar_send_button']")
            if not send_button:
                logger.warning(f"❌ Кнопка отправки не найдена в чате {chat_id}")
                continue

            # Клик по кнопке
            box = await send_button.bounding_box()
            if box:
                await page.mouse.move(box["x"] + 5, box["y"] + 5)
                await page.wait_for_timeout(150)

            await send_button.click()
            logger.info(f"✅ Сообщение отправлено в чат {chat_id}")

            try:
                # Ждём, пока элемент последнего сообщения появится
                await page.wait_for_selector("#thread_page_last_item", timeout=7000)

                # Получаем текст последнего сообщения
                last_item_text = await page.inner_text("#thread_page_last_item")

                short_text = message_text.strip().split("\n")[0][:50]

                if short_text.lower() in last_item_text.lower():
                    logger.info(
                        f"📨 Последнее сообщение содержит отправленный текст — подтверждено в чате {chat_id}")
                else:
                    logger.warning(f"⚠️ Последнее сообщение не совпадает с ожидаемым текстом в чате {chat_id}")
            except PlaywrightTimeoutError:
                logger.error(f"❌ Элемент последнего сообщения (#thread_page_last_item) не найден в чате {chat_id}")

        except Exception as e:
            logger.warning(f"⚠️ Ошибка при работе с чатом {chat_id}: {e}")
            try:
                os.makedirs("output", exist_ok=True)

                html_debug = await page.content()
                html_path = OUTPUT_DIR / f"debug_chat_{chat_id}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_debug)
                logger.info(f"💾 HTML сохранён: {html_path}")

                screenshot_path = OUTPUT_DIR / f"chat_error_{chat_id}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"📸 Скриншот сохранён: {screenshot_path}")

            except Exception as inner_e:
                logger.error(f"❌ Не удалось сохранить HTML или скриншот: {inner_e}")


async def process_messages(page: Page):
    count, unread = await get_message_data(page)
    logger.info(f"🎯 Обнаружено {count} новых сообщений.")

    with open(UNREAD_MESSAGES_PATH, "r", encoding="utf-8") as f:
        unread_data = json.load(f)

    chat_details = []
    for chat in unread_data:
        try:
            details = await parse_chat_details(page, chat["id"])
            if details:
                chat_details.append(details)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при обработке чата {chat['id']}: {e}")
            continue

    return count, chat_details


async def save_chat_context(chat_details):
    with open(CHAT_CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(chat_details, f, ensure_ascii=False, indent=2)
    logger.info("💾 Контекст чатов сохранён.")


async def generate_openai_responses():
    start = time.monotonic()
    responses = await openai_api.generate_responses()
    elapsed = time.monotonic() - start
    logger.info(f"🧠 Генерация ответов OpenAI заняла {elapsed:.2f} сек.")
    return responses


async def find_chat_element_by_id(page: Page, chat_id: str) -> ElementHandle | None:
    await page.goto("https://www.airbnb.com/hosting/messages/")
    await page.wait_for_selector("div[data-listrow='true']", timeout=10000)
    rows = await page.query_selector_all("div[data-listrow='true']")
    for el in rows:
        inner_div = await el.query_selector(f'div[id="inbox_list_{chat_id}"]')
        if inner_div:
            return el
    return None


async def send_all_responses(page, responses, unread_elements):
    responses_dict = {r["id"]: r["reply"] for r in responses}
    chat_ids_to_send = [chat_id for _, chat_id in unread_elements if chat_id in responses_dict]

    for chat_id in chat_ids_to_send:
        await send_message_to_unread(page, [chat_id], responses_dict[chat_id])


def log_system_resources(stage=""):
    process = psutil.Process(os.getpid())
    cpu_usage = process.cpu_percent(interval=1)
    memory = process.memory_info().rss / (1024 * 1024)
    logger.info(f"{stage} — CPU: {cpu_usage}% | RAM: {memory:.2f} MB")


is_logged_in = False  # глобальный флаг авторизации


async def run_once(first_run=False):
    global is_logged_in
    logger.info("🚀 Запуск скрипта...")

    try:
        async with async_playwright() as p:
            context, page = await prepare_browser(p)

            if first_run or not is_logged_in:
                logger.info("🔐 Проверка входа в аккаунт (первый запуск)...")
                if not await check_logged_in(page):
                    logger.error("❌ Вход не выполнен. Завершение.")
                    raise AutoStopError("🔐 Выход из аккаунта Airbnb")
                is_logged_in = True

            count, chat_details = await process_messages(page)
            log_system_resources(stage="⏱️ Проверка сообщений")

            if count == 0:
                logger.info("📭 Новых сообщений нет — генерация ответов OpenAI не требуется.")
                return

            if not chat_details:
                logger.warning("⚠️ Контексты чатов пусты — генерация невозможна.")
                return

            await save_chat_context(chat_details)

            responses = await generate_openai_responses()
            log_system_resources(stage="🧠 После генерации OpenAI")

            if not responses:
                logger.error("❌ Ответы от OpenAI не получены — ничего не отправляется.")
                return

            # Здесь ты можешь вытащить индексы из контекста и сформировать unread_elements:
            unread_elements = []
            for detail in chat_details:
                el = await find_chat_element_by_id(page, detail["id"])
                if el:
                    unread_elements.append((el, detail["id"]))

            await send_all_responses(page, responses, unread_elements)

    except Exception as e:
        logger.exception("💥 Ошибка в run_once: возможно, аккаунт больше не авторизован.")
        raise


async def scheduler(interval_seconds: int = 180):
    first_run = True
    try:
        while True:
            await run_once(first_run=first_run)
            first_run = False
            logger.info(f"⏳ Следующая проверка через {interval_seconds} сек...\n")
            await asyncio.sleep(interval_seconds)

    except AutoStopError as e:
        logger.warning(f"🛑 Автоответчик остановлен автоматически: {e}")
        await notify_admins(f"❗️ Автоответчик остановлен: {e}")

    except asyncio.CancelledError:
        logger.info("🛑 Работа остановлена пользователем через .cancel()")

    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt — Завершение скрипта")

    except Exception as e:
        logger.critical(f"💥 Критическая ошибка в scheduler: {e}")
        await notify_admins(f"Произошла неизвестная ошибка, перешлите разработчику! Ошибка: {e}")
