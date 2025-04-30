import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup, MessageEntity
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    DispatcherHandlerStop
)
from telegram.utils.request import Request

# --- НАСТРОЙКА ЛОГОВ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПОЛУЧАЕМ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# --- ДАННЫЕ О ГОРОДАХ и ТЕСТОВЫХ ЧАТАХ ---
ALL_CITIES = [
    {"name": "Тюмень",        "date": "31.05.2024", "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy",  "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi",  "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi",  "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy",  "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy",  "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUJmNzhi",  "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi",  "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",        "date": "15.04.2025", "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",   "link": "https://t.me/+Dpb3ozk_4Dc5OTYy",  "chat_id": -1002438533236},
    {"name": "Донецк",        "link": "https://t.me/+nGkS5gfvvQxjNmRi",  "chat_id": -1002328107804},
    {"name": "Хабаровск",     "link": "https://t.me/+SrnvRbMo3bA5NzVi",  "chat_id": -1002480768813},
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy",  "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# Список ID пользователей, которым разрешено использовать бота
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Для удобства создадим lookup-систему: chat_id -> название
city_lookup = {city["chat_id"]: city["name"] for city in ALL_CITIES}

# --- СОЗДАЁМ БОТА И ДИСПЕТЧЕР ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПРЕМИУМ-ЭМОДЗИ И ССЫЛОК ---
def rebuild_text_with_entities(msg) -> str:
    """
    Преобразует msg.text и msg.entities в HTML-строку,
    сохраняя ссылки, форматирование и кастом-эмодзи.
    """
    if not msg.text:
        return ""
    text = msg.text
    entities = msg.entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset+e.length, reverse=True):
        s, e = ent.offset, ent.offset + ent.length
        if ent.type == "bold":
            chars.insert(e, "</b>")
            chars.insert(s, "<b>")
        elif ent.type == "italic":
            chars.insert(e, "</i>")
            chars.insert(s, "<i>")
        elif ent.type == "underline":
            chars.insert(e, "</u>")
            chars.insert(s, "<u>")
        elif ent.type == "strikethrough":
            chars.insert(e, "</s>")
            chars.insert(s, "<s>")
        elif ent.type == "code":
            chars.insert(e, "</code>")
            chars.insert(s, "<code>")
        elif ent.type == "link":
            url = ent.url
            segment = ''.join(chars[s:e])
            del chars[s:e]
            chars.insert(s, f'<a href="{url}">{segment}</a>')
        elif ent.type == MessageEntity.CUSTOM_EMOJI:
            emoji_id = ent.custom_emoji_id
            del chars[s:e]
            chars.insert(s, f'<emoji emoji_id="{emoji_id}"/>')
    return ''.join(chars)

# --- Существующая caption-функция расширяем под кастом-эмодзи ---
def rebuild_caption_with_entities(update: Update) -> str:
    if not update.message.caption:
        return ""
    text = update.message.caption
    entities = update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        if ent.type == "bold":
            chars.insert(end, "</b>")
            chars.insert(start, "<b>")
        elif ent.type == "italic":
            chars.insert(end, "</i>")
            chars.insert(start, "<i>")
        elif ent.type == "underline":
            chars.insert(end, "</u>")
            chars.insert(start, "<u>")
        elif ent.type == "strikethrough":
            chars.insert(end, "</s>")
            chars.insert(start, "<s>")
        elif ent.type == "code":
            chars.insert(end, "</code>")
            chars.insert(start, "<code>")
        elif ent.type == "spoiler":
            chars.insert(end, "</u>")
            chars.insert(start, "<u>")
        elif ent.type == MessageEntity.CUSTOM_EMOJI:
            emoji_id = ent.custom_emoji_id
            del chars[start:end]
            chars.insert(start, f'<emoji emoji_id="{emoji_id}"/>')
    return ''.join(chars)

# --- ФУНКЦИИ ОТПРАВКИ ---
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    attempt = 1
    while attempt <= max_attempts:
        try:
            sent_message = bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML")
            logging.info(f"Сообщение отправлено в чат {chat_id}, message_id={sent_message.message_id}")
            return sent_message
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке текста в {chat_id}: {e}")
            if "Chat not found" in str(e):
                return None
            attempt += 1
            time.sleep(delay)
    return None

# Функция мультимедиа без изменений
# (оставляем rebuild_caption_with_entities для caption)

def forward_multimedia(update: Update, chat_id):
    new_caption = rebuild_caption_with_entities(update)
    logging.info("..."
    )
    # (ваша существующая логика send_photo/send_video и т.д.)
    
# В handler forward_message заменяем bot.copy_message на send_message/send_media с rebuild_text_with_entities

def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    if not msg or msg.chat.type != "private":
        return

    # ... ваш выбор pending_test ...

    chat_ids = context.user_data.get("selected_chats", [])
    if not chat_ids:
        msg.reply_text("Сначала выберите действие, используя команду /menu.")
        return

    failures = []
    for cid in chat_ids:
        try:
            # если текст
            if msg.text:
                html = rebuild_text_with_entities(msg)
                bot.send_message(chat_id=cid, text=html, parse_mode="HTML", disable_web_page_preview=True)
            else:
                forward_multimedia(update, cid)
            logging.info(f"Переслано сообщение {msg.message_id} → чат {cid}")
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение в чат {cid}: {e}")
            failures.append(cid)

    # ... ответ пользователю и очистка состояния ...

# Остальные handlers без изменений

app = Flask(__name__)
@app.route('/webhook', methods=['POST'])
 def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Запуск Flask-сервера на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
