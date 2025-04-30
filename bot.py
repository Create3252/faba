import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
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

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# --- СПИСОК ГОРОДОВ И ТЕСТОВЫХ ЧАТОВ ---
ALL_CITIES = [
    {"name": "Тюмень",         "date": "31.05.2024", "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",    "link": "https://t.me/+wx20YVCwxmo3YmQy",  "chat_id": -1002489311984},
    {"name": "Сахалин",        "link": "https://t.me/+FzQ_jEYX8AtkMzNi",  "chat_id": -1002265902434},
    {"name": "Красноярск",     "link": "https://t.me/+lMTDVPF0syRiYzdi",  "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва",         "link": "https://t.me/+qokFNNnfhQdiYjQy",  "chat_id": -1002182445604},
    {"name": "Екатеринбург",   "link": "https://t.me/+J2ESyZJyOAk2YzYy",  "chat_id": -1002392430562},
    {"name": "Иркутск",        "link": "https://t.me/+TAoCnfoePUJmNzhi",  "chat_id": -1002255012184},
    {"name": "Оренбург",       "link": "https://t.me/+-Y_1N0HnePUxZjZi",  "chat_id": -1002316600732},
    {"name": "Крым",           "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",           "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",      "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",      "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",          "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",         "date": "15.04.2025", "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",    "link": "https://t.me/+Dpb3ozk_4Dc5OTYy",  "chat_id": -1002438533236},
    {"name": "Донецк",         "link": "https://t.me/+nGkS5gfvvQxjNmRi",  "chat_id": -1002328107804},
    {"name": "Хабаровск",      "link": "https://t.me/+SrnvRbMo3bA5NzVi",  "chat_id": -1002480768813},
    {"name": "Челябинск",      "link": "https://t.me/+ZKXj5rmcmMw0MzQy",  "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- СПИСОК ПРАВ ---
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 1283190854, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Для отображения списка городов
city_lookup = {c["chat_id"]: c["name"] for c in ALL_CITIES}


# --- СОЗДАЁМ БОТА И ДИСПЕТЧЕР ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)


# --- ФУНКЦИЯ ОТПРАВКИ С ПОВТОРНЫМИ ПОПЫТКАМИ ---
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    attempt = 1
    while attempt <= max_attempts:
        try:
            sent = bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML")
            logging.info(f"[Retry] Sent to {chat_id}, msg_id={sent.message_id}")
            return sent
        except Exception as e:
            logging.error(f"[Retry {attempt}] Error sending to {chat_id}: {e}")
            attempt += 1
            time.sleep(delay)
    return None


# --- МЕНЮ /menu ---
def menu(update: Update, context: CallbackContext):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("❌ Нет доступа.")
        return
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))


# --- ОБРАБОТКА ВЫБОРА МЕНЮ (группа 0) ---
def handle_main_menu(update: Update, context: CallbackContext):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        return
    if not context.user_data.get("pending_main_menu"):
        return
    text = update.message.text.strip()
    # Список чатов
    if text == "Список чатов ФАБА":
        lines = ["<b>Список чатов ФАБА:</b>"]
        for city in ALL_CITIES:
            if city.get("link"):
                lines.append(f"<a href='{city['link']}'>{city['name']}</a>")
            else:
                lines.append(city["name"])
        markup = ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)
        context.user_data.clear()
        raise DispatcherHandlerStop

    # Отправить всем
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text("Отправьте сообщение для рассылки во все чаты.", reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True))
        context.user_data.clear()
        raise DispatcherHandlerStop

    # Тестовая отправка
    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите текст или отправьте медиа для тестовой отправки.", reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True))
        context.user_data.clear()
        raise DispatcherHandlerStop

    # Назад
    if text == "Назад":
        menu(update, context)
        context.user_data.clear()
        raise DispatcherHandlerStop

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu), group=0)


# --- ПЕРЕСЫЛКА СООБЩЕНИЙ (группа 1) ---
def forward_any(update: Update, context: CallbackContext):
    msg = update.message
    if not msg or msg.chat.type != "private":
        return

    # Тестовая отправка
    if context.user_data.get("pending_test"):
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"[Test send] {e}")
        msg.reply_text("✅ Тестовая отправка выполнена.")
        return

    # Отправка в выбранные после "Отправить сообщение во все чаты"
    selected = context.user_data.get("selected_chats", [])
    if selected:
        for cid in selected:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"[Bulk send] {e}")
        msg.reply_text("✅ Сообщение отправлено.")
        context.user_data.clear()
        return

    # Иначе – ничего не делаем
    msg.reply_text("Используйте /menu для выбора действия.")

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, forward_any), group=1)


# --- Функции /edit, /delete, /getid (по аналогии с тем, что было) ---
# (вставляй сюда свои текущие реализации, если нужно)


# --- FLASK И ВЕБХУК ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
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
    logging.info(f"Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
