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
    CallbackContext
)
from telegram.utils.request import Request

# --- НАСТРОЙКА ЛОГОВ ---
logging.basicConfig(
    format='%((asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПОЛУЧАЕМ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Нужно задать BOT_TOKEN и WEBHOOK_URL")

# --- ДАННЫЕ О ГОРОДАХ и ТЕСТОВЫХ ЧАТАХ ---
ALL_CITIES = [
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
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
    {"name": "Самара",        "link": "https://t.me/+SLCllcYKCUFlNjk6",  "chat_id": -1002589409715},
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
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 533007308, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# --- СОЗДАЁМ БОТА И ДИСПЕТЧЕР ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- КОМАНДА /menu ---
def menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    context.user_data["pending_main"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА ВЫБОРА В МЕНЮ (group=0) ---
def main_menu(update: Update, context: CallbackContext):
    if not context.user_data.pop("pending_main", False):
        return
    text = update.message.text

    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for c in ALL_CITIES:
            if c["link"]:
                lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
            else:
                lines.append(c["name"])
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True, resize_keyboard=True)
        )

    elif text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text("Теперь пришлите любое сообщение (текст, медиа). После — подсказка /menu.")

    elif text == "Тестовая отправка":
        context.user_data["test"] = True
        update.message.reply_text("Пришлите сообщение для тестовой рассылки.")

    elif text == "Назад":
        return menu(update, context)

    else:
        update.message.reply_text("Неверный выбор. Введите /menu.")

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, main_menu),
    group=0
)

# --- ПЕРЕСЫЛКА ВСЕХ МЕДИА И ТЕКСТА (group=1) ---
def forward_all(update: Update, context: CallbackContext):
    msg = update.message

    # тестовая рассылка
    if context.user_data.pop("test", False):
        targets = TEST_SEND_CHATS
    else:
        targets = context.user_data.pop("selected", [])

    if not targets:
        return msg.reply_text("Сначала введите /menu")

    failures = []
    for cid in targets:
        try:
            # копируем полностью — сохраняются формат, ссылки, премиум-эмодзи
            bot.copy_message(
                chat_id=cid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
            logging.info(f"Скопировано {msg.message_id} → {cid}")
        except Exception as e:
            logging.error(f"Не удалось скопировать в {cid}: {e}")
            failures.append(cid)

    if failures:
        failed_str = ", ".join(str(x) for x in failures)
        msg.reply_text(f"Не дошло в: {failed_str}\n/menu")
    else:
        msg.reply_text("Разослано успешно.\n/menu")

dispatcher.add_handler(
    MessageHandler(~Filters.command & Filters.chat_type.private, forward_all),
    group=1
)

# --- Flask и Webhook ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
