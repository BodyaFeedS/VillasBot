import os
import re
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Очищаем список каналов от лишних символов (ссылок https://t.me/ или знака @)
raw_channels = os.getenv("CHANNELS", "").split(",")
CHANNELS = []
for ch in raw_channels:
    ch = ch.strip()
    if not ch:
        continue
    ch = re.sub(r'^(?:https?://)?(?:t\.me/)?@?', '', ch).strip('/')
    if ch:
        CHANNELS.append(ch)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
MAX_PRICE = int(os.getenv("MAX_PRICE", 1000))
DEFAULT_EXCHANGE_LIMIT = int(os.getenv("DEFAULT_EXCHANGE_LIMIT", 50000))

# Ключи для реальных нейросетей (OpenAI или Google Gemini)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
