import asyncio
import json
from openai import AsyncOpenAI
from typing import List
from dotenv import load_dotenv
import os
import config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

client = AsyncOpenAI(api_key=os.getenv('OPENAI_API'))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
CHAT_CONTEXT_PATH = config.CHAT_CONTEXT_PATH


def load_contexts_from_file(path: str = CHAT_CONTEXT_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(messages: List[str], reservation: str, guest_info: str) -> str:
    chat = "\n".join(messages)
    prompt = (
        f"Ты — хост квартиры на Airbnb. Сгенерируй вежливый, дружелюбный и полезный ответ гостю на основе последних сообщений в чате.\n"
        f"\nКонтекст:\n"
        f"{chat}\n"
        f"\nИнформация о бронировании: {reservation}\n"
        f"Информация о госте: {guest_info}\n"
        f"\nОтветь от лица хоста, максимально естественно и человечно.\n"
        f"Если в контексте было приветствие, то не нужно его писать."
        f"Не нужно прощаться и писать наилучшие пожелания."
        f"Это переписка в чате, а не email"
        f"Все общение должно быть строго на английском"
        f"Если в сообщениях есть вопросы от Гостя на которые не было ответов от Хоста, то отвечай на них"

    )
    return prompt


async def generate_responses():
    contexts = load_contexts_from_file()
    responses = []

    for block in contexts:
        prompt = build_prompt(
            block["last_messages"],
            block["reservation"],
            block["guest_info"]
        )

        thread = await client.beta.threads.create()

        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )

        run = await client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        while True:
            run = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status == "completed":
                break
            elif run.status in ["failed", "cancelled"]:
                print(f"❌ Ошибка: {run.status}")
                break
            await asyncio.sleep(1)

        messages = await client.beta.threads.messages.list(thread_id=thread.id)
        assistant_message = next(
            (m for m in messages.data if m.role == "assistant"),
            None
        )

        if assistant_message:
            responses.append({
                "id": block["id"],  # заменено с index
                "reply": assistant_message.content[0].text.value.strip()
            })

    with open(config.RESPONSES_PATH, "w", encoding="utf-8") as f:
        json.dump(responses, f, ensure_ascii=False, indent=2)

    return responses
