# import logging
# import asyncio
# import os
# from bot_instance import bot  # твой уже инициализированный bot
#
# # ID администратора, куда отправлять ошибки
#
# ADMIN_IDS = list(map(int, os.getenv("ADMINS", "").split(',')))
#
#
# class TelegramErrorHandler(logging.Handler):
#     def __init__(self, level=logging.ERROR):
#         super().__init__(level)
#
#     def emit(self, record):
#         log_entry = self.format(record)
#         asyncio.create_task(self.send_telegram_message(log_entry))
#
#     async def send_telegram_message(self, message: str):
#         for id in ADMIN_IDS:
#             try:
#                 await bot.send_message(id, f"❗️Лог ошибки:\n{message[:4000]}")
#             except Exception as e:
#                 logging.getLogger(__name__).warning(f"❌ Не удалось отправить лог в Telegram: {e}")
