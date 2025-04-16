import asyncio
import logging
from aiogram import Bot, Dispatcher
from handlers import main_handler
from bot_instance import bot
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn
from api.api_service import router as api_router

log_file_path = "logfile.log"
log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter(log_format))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

dp = Dispatcher()
app = FastAPI()
app.include_router(api_router, prefix="")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


async def bot_main():
    dp.include_routers(main_handler.router)
    print("✅ База данных инициализирована")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(bot_main())
    uvicorn.run(app, host="0.0.0.0", port=8080)
