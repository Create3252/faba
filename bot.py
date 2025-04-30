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

# --- ФУНКЦИЯ РАЗБОРА caption_entities ---
def rebuild_caption_with_entities(update: Update) -> str:
    if not update.message.caption:
        return ""
    text = update.message.caption
    entities = update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        tags = {
            'bold': ('<b>', '</b>'),
            'italic': ('<i>', '</i>'),
            'underline': ('<u>', '</u>'),
            'strikethrough': ('<s>', '</s>'),
            'code': ('<code>', '</code>'),
            'spoiler': ('<u>', '</u>'), # заменяем на underline
        }
        if ent.type in tags:
            op, cl = tags[ent.type]
            chars.insert(end, cl)
            chars.insert(start, op)
    return "".join(chars)

# --- ФУНКЦИЯ ОТПРАВКИ С ПОВТОРНЫМИ ПОПЫТКАМИ ---
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    attempt = 1
    while attempt <= max_attempts:
        try:
            sent_message = bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            logging.info(f"Сообщение отправлено в чат {chat_id}, message_id={sent_message.message_id}")
            return sent_message
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке текста в {chat_id}: {e}")
            if "Chat not found" in str(e):
                return None
            attempt += 1
            time.sleep(delay)
    return None

# --- ФУНКЦИЯ ПЕРЕСЫЛКИ МЕДИА ---
def forward_multimedia(update: Update, chat_id):
    new_caption = rebuild_caption_with_entities(update)
    if update.message.photo:
        return bot.send_photo(
            chat_id=chat_id,
            photo=update.message.photo[-1].file_id,
            caption=new_caption,
            parse_mode="HTML",
            disable_notification=False
        )
    if update.message.video:
        return bot.send_video(
            chat_id=chat_id,
            video=update.message.video.file_id,
            caption=new_caption,
            parse_mode="HTML"
        )
    if update.message.audio:
        return bot.send_audio(
            chat_id=chat_id,
            audio=update.message.audio.file_id,
            caption=new_caption,
            parse_mode="HTML"
        )
    if update.message.document:
        return bot.send_document(
            chat_id=chat_id,
            document=update.message.document.file_id,
            caption=new_caption,
            parse_mode="HTML"
        )
    # fallback
    return send_message_with_retry(chat_id, update.message.text)

# --- ГЛАВНОЕ МЕНЮ (/menu) ---
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА МЕНЮ (group=0) ---
def handle_main_menu(update: Update, context: CallbackContext) -> bool:
    text = update.message.text.strip()
    if "pending_main_menu" not in context.user_data:
        return False
    # ... остальная логика меню без изменений ...

# --- ПЕРЕСЫЛКА СООБЩЕНИЙ (group=1) ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    # ... логика с bot.copy_message без изменений ...

# Регистрация handler'ов и Flask-приложение тоже без изменений

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
