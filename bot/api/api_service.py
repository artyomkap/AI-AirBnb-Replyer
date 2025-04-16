import json
import logging
import os
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from airbnb_service.autosender import scheduler
from airbnb_service import state
from bot_instance import bot
from config import COOKIES_PATH

router = APIRouter()
logger = logging.getLogger(__name__)
ADMIN_IDS = list(map(int, os.getenv("ADMINS", "").split(',')))


class CookiePayload(BaseModel):
    cookies: str


@router.post("/api/save_cookies")
async def save_cookies(payload: CookiePayload):
    try:
        try:
            cookies_data = json.loads(payload.cookies)
        except json.JSONDecodeError:
            logger.warning("⛔ Не удалось декодировать cookies.")
            return {"status": "error", "detail": "Invalid cookies format."}

        os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
        with open(COOKIES_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies_data, f, ensure_ascii=False, indent=2)

        logger.info("✅ Cookies обновлены.")
        await notify_admins("✅ Cookies обновлены на сервере")
        # Запуск автоответчика
        if state.scheduler_task and not state.scheduler_task.done():
            logger.info("⚠️ Scheduler уже запущен.")
            return {"status": "already_running"}

        state.scheduler_task = asyncio.create_task(run_scheduler_with_ui())
        logger.info("🚀 Автоответчик запущен.")
        await notify_admins("🚀 Автоответчик запущен")
        return {"status": "ok"}

    except Exception as e:
        logger.exception("Ошибка при сохранении cookies")
        return {"status": "error", "detail": str(e)}


@router.post("/api/stop_scheduler")
async def stop_scheduler():
    if state.scheduler_task and not state.scheduler_task.done():
        state.scheduler_task.cancel()
        state.scheduler_running = False
        logger.info("🛑 Scheduler остановлен пользователем.")
        await notify_admins("🛑 Автоответчик остановлен вручную.")
        return {"status": "stopped"}
    return {"status": "not_running"}


async def run_scheduler_with_ui():
    state.scheduler_running = True
    try:
        await scheduler()
    except asyncio.CancelledError:
        logger.info("🛑 Scheduler остановлен вручную.")
        await notify_admins("🛑 Автоответчик остановлен вручную.")
    except RuntimeError as e:
        logger.warning(f"⛔️ Scheduler остановлен: {e}")
        await notify_admins(f"⛔️ Автоответчик остановлен: {e}")
    except Exception as e:
        logger.exception("❗ Ошибка в автоответчике.")
        await notify_admins(f"💥 Ошибка автоответчика: {e}")
    finally:
        state.scheduler_running = False


async def notify_admins(text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить сообщение админу {admin_id}: {e}")
