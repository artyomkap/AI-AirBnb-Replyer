import asyncio
import json
import logging
import os
import aiofiles
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, Document
import config
from airbnb_service.autosender import scheduler
from bot_instance import bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

router = Router()
ADMIN_IDS = list(map(int, os.getenv("ADMINS", "").split(',')))
logger = logging.getLogger(__name__)
scheduler_running = {}
scheduler_task = {}


class CookiesState(StatesGroup):
    waiting_for_file = State()


COOKIES_PATH = config.COOKIES_PATH


def get_control_keyboard():
    text = "🟢 Остановить автоответчик" if scheduler_running else "⚪ Включить автоответчик"
    callback_data = "stop_scheduler" if scheduler_running else "start_scheduler"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data)],
            [InlineKeyboardButton(text='🍪 Обновить куки', callback_data='update_cookies')]
        ]
    )


async def run_scheduler_with_ui(user_id):
    global scheduler_running
    try:
        await scheduler()
    except asyncio.CancelledError:
        logger.info("🛑 Scheduler остановлен вручную.")
    except Exception as e:
        logger.exception("❗ Ошибка в автоответчике.")
        await bot.send_message(user_id, text=f"💥 Ошибка автоответчика: {e}")
    finally:
        scheduler_running = False
        await bot.send_message(user_id, text="❌ Автоответчик аварийно остановлен.", reply_markup=get_control_keyboard())


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        await message.answer('🚫 Доступ закрыт!')
        return

    # Если куки есть — запускаем основное меню
    await message.answer("🧠 Welcome to AIRBNB AutoReplier 🧠", reply_markup=get_control_keyboard())


@router.callback_query(F.data.in_({"start_scheduler", "stop_scheduler"}))
async def toggle_scheduler(call: CallbackQuery):
    global scheduler_task, scheduler_running
    user_id = call.from_user.id
    if call.data == "start_scheduler":
        if not scheduler_running:
            scheduler_task = asyncio.create_task(run_scheduler_with_ui(user_id))
            scheduler_running = True
            await bot.send_message(call.from_user.id, text="✅ Автоответчик запущен!",
                                   reply_markup=get_control_keyboard())
        else:
            await call.answer("⚠️ Уже запущено.")

    elif call.data == "stop_scheduler":
        if scheduler_task and not scheduler_task.done():
            scheduler_task.cancel()
            scheduler_running = False
            await bot.send_message(call.from_user.id, text="🛑 Автоответчик остановлен.",
                                   reply_markup=get_control_keyboard())
        else:
            await call.answer("⚠️ Уже остановлено.")


@router.callback_query(F.data == 'update_cookies')
async def start_file_upload(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📎 Пожалуйста, отправьте файл с куками в формате <code>cookies.json</code>.\n\nДля отмены нажмите /cancel."
    )
    await state.set_state(CookiesState.waiting_for_file)
    await callback.answer()


@router.message(F.text == "/cancel")
async def cancel_upload(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Загрузка cookies отменена.")


@router.message(CookiesState.waiting_for_file, F.document)
async def handle_file_upload(message: Message, state: FSMContext):
    document: Document = message.document

    if not document.file_name.endswith(".json"):
        await message.answer("⚠️ Неверный формат файла. Пожалуйста, отправьте JSON-файл.")
        return

    file = await message.bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await message.bot.download_file(file.file_path, file_path)

    try:
        async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении файла: {e}")
        os.remove(file_path)
        return

    os.remove(file_path)

    # Сохраняем в основной файл
    try:
        async with aiofiles.open(COOKIES_PATH, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=4, ensure_ascii=False))
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении cookies.json: {e}")
        return

    await message.answer("✅ Cookies успешно обновлены.")
    await state.clear()
