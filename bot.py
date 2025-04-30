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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
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
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy",  "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy",  "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUJmNzhi",  "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi",  "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",        "date": "15.04.2025", "link": "https://t.me/+SLCllcYKCUFlNjk6","chat_id": -1002589409715},
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
ALLOWED_USER_IDS = [
    296920330,
    320303183,
    533773,
    327650534,
    533007308,   # ваш дополнительный ID
    136737738,
    1607945564
]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Инициализация бота и диспетчера
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# Преобразование caption + entities в HTML
def rebuild_caption_with_entities(update: Update) -> str:
    if not update.message.caption:
        return ""
    text = update.message.caption
    entities = update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        tag = {
            "bold": ("<b>", "</b>"),
            "italic": ("<i>", "</i>"),
            "underline": ("<u>", "</u>"),
            "strikethrough": ("<s>", "</s>"),
            "code": ("<code>", "</code>"),
            "spoiler": ("<u>", "</u>")
        }.get(ent.type, ("", ""))
        chars.insert(end, tag[1])
        chars.insert(start, tag[0])
    return "".join(chars)

# Отправка текста с retry и без предпросмотра
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    for attempt in range(1, max_attempts+1):
        try:
            return bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке в {chat_id}: {e}")
            if "Chat not found" in str(e):
                return None
            time.sleep(delay)
    return None

# Основное меню /menu
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup, disable_web_page_preview=True)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# Обработка выбора меню (group=0)
def handle_main_menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return False
    text = update.message.text.strip()
    if "pending_main_menu" not in context.user_data:
        return False

    if text == "Назад":
        context.user_data.pop("pending_main_menu", None)
        return menu(update, context)

    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for city in ALL_CITIES:
            if city.get("link"):
                lines.append(f"<a href='{city['link']}'>{city['name']}</a>")
            else:
                lines.append(city["name"])
        back = ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=back
        )
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text(
            "Теперь отправьте сообщение.\nДля отмены нажмите /menu",
            disable_web_page_preview=True
        )
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите текст или медиа для тестовой отправки.", disable_web_page_preview=True)
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    update.message.reply_text("Неверно. Нажмите /menu.", disable_web_page_preview=True)
    context.user_data.pop("pending_main_menu", None)
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu),
    group=0
)

# Пересылка (group=1)
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    if msg.chat.type != "private":
        return

    # тестовая
    if context.user_data.get("pending_test"):
        context.user_data.pop("pending_test", None)
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                failures.append(cid)
        text = ("Ошибка в тестовых чатах: "
                + ", ".join(str(x) for x in failures)) if failures else "Тестовое сообщение отправлено."
        return msg.reply_text(text, disable_web_page_preview=True)

    # обычная
    chat_ids = context.user_data.get("selected_chats", [])
    if not chat_ids:
        return msg.reply_text("Сначала /menu", disable_web_page_preview=True)

    failures = []
    for cid in chat_ids:
        try:
            bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        except Exception as e:
            failures.append(cid)

    if failures:
        text = "Часть сообщений не ушла в: " + ", ".join(str(x) for x in failures)
    else:
        text = "Сообщение успешно доставлено."
    msg.reply_text(text + "\n/menu", disable_web_page_preview=True)

    context.user_data.pop("selected_chats", None)

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message),
    group=1
)

# /edit, /delete, /getid (приведены без изменений)
def edit_message(update: Update, context: CallbackContext):
    # ... ваш существующий код ...
    pass

def delete_message(update: Update, context: CallbackContext):
    # ... ваш существующий код ...
    pass

def get_chat_id(update: Update, context: CallbackContext):
    update.message.reply_text(f"ID: {update.message.chat.id}", disable_web_page_preview=True)

dispatcher.add_handler(CommandHandler("getid", get_chat_id))

# Flask и вебхук
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
