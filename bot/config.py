import os
from dotenv import load_dotenv

load_dotenv()

# 📁 Путь к папке config.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# 📁 Путь к корню проекта (AutoMessagesAirBnB)
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, "."))

# 📂 Абсолютные пути к файлам
AIRBNB_MESSAGES_PATH = os.path.join(PROJECT_DIR, "airbnb_service", "output", "airbnb_messages.html")
CHAT_CONTEXT_PATH = os.path.join(PROJECT_DIR, "airbnb_service", "output", "chat_context.json")
RESPONSES_PATH = os.path.join(PROJECT_DIR, "airbnb_service", "output", "responses.json")
UNREAD_MESSAGES_PATH = os.path.join(PROJECT_DIR, "airbnb_service", "output", "unread_messages.json")
COOKIES_PATH = os.path.join(PROJECT_DIR, "airbnb_service", "cookies.json")

# 🔑 Ключи и ID для OpenAI
OPENAI_API = os.getenv("OPENAI_API")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_URL = os.getenv('DB_URL')