import os
import re
from dotenv import load_dotenv

# Загрузка переменных окружения из .env (если файл существует)
load_dotenv()

# Токен бота (с надежным fallback на случай отсутствия .env на сервере хостинга / Render)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8835292843:AAGTbcKGHVB1H6Pe3dfyTJwJsSvkNOYN8kw").strip()

# Очищаем список каналов от лишних символов (ссылок https://t.me/ или знака @)
# Исключаем каналы обмена валют (exchange) и гарантируем отслеживание профильных каналов вилл:
# @nedvizhka_Ciprus и @kvartiry_cyprus
raw_channels_str = os.getenv("CHANNELS", "nedvizhka_Ciprus,kvartiry_cyprus")
raw_channels = raw_channels_str.split(",")
CHANNELS = []
for ch in raw_channels:
    ch = ch.strip()
    if not ch:
        continue
    ch = re.sub(r'^(?:https?://)?(?:t\.me/)?@?', '', ch).strip('/')
    if ch and ch not in CHANNELS and "exchange" not in ch.lower():
        CHANNELS.append(ch)

# Гарантируем, что оба ключевых канала всегда отслеживаются, даже если в .env указан только один
for default_ch in ["nedvizhka_Ciprus", "kvartiry_cyprus"]:
    if default_ch not in CHANNELS:
        CHANNELS.append(default_ch)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
MAX_PRICE = int(os.getenv("MAX_PRICE", 600))
DEFAULT_EXCHANGE_LIMIT = 50000

# Ключи для реальных нейросетей (OpenAI или Google Gemini)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LAYIDCIHIqdEBoKmJeS6hD9VHBvxLoFcH3HrUNhPJB5w").strip()
