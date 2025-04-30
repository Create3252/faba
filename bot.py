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

# --- ПОЛУЧАЕМ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- ДАННЫЕ О ГОРОДАХ и ТЕСТОВЫХ ЧАТАХ ---
ALL_CITIES = [
    {"name": "Тюмень", "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск", "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин", "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск", "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург", "link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва", "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург", "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск", "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург", "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым", "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002374636424},
    {"name": "Чита", "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград", "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар", "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь", "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара", "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток", "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк", "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск", "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск", "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]
forwarded_messages = {}

# --- ИНИЦИАЛИЗАЦИЯ ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- МЕНЮ ---
def menu(update: Update, context: CallbackContext):
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

def handle_main_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS or "pending_main_menu" not in context.user_data:
        return
    text = update.message.text.strip()
    # Кнопка Назад сразу возвращает в меню
    if text == "Назад":
        context.user_data.pop("pending_main_menu", None)
        menu(update, context)
        raise DispatcherHandlerStop
    # Список чатов
    if text == "Список чатов ФАБА":
        lines = [f"<a href='{c['link']}'>{c['name']}</a>" for c in ALL_CITIES]
        update.message.reply_text(
            "Список чатов:\n" + "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        )
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop
    # Все чаты
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text("Напишите сообщение для рассылки.\nПосле отправки нажмите /menu")
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop
    # Тестовая
    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите текст или медиа для тестовой отправки.\nПосле отправки нажмите /menu")
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu), group=0)

# --- ПЕРЕСЫЛКА ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    # Тестовая
    if context.user_data.get("pending_test"):
        context.user_data.pop("pending_test")
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(cid, msg.chat.id, msg.message_id)
            except:
                failures.append(cid)
        text = ("Часть не доставлено: " + ", ".join(map(str, failures))) if failures else "Тестовая рассылка успешна."
        msg.reply_text(text + "\nНажмите /menu")
        return
    # Основная
    chat_ids = context.user_data.get("selected_chats", [])
    if not chat_ids:
        msg.reply_text("Сначала нажмите /menu")
        return
    failures = []
    for cid in chat_ids:
        try:
            bot.copy_message(cid, msg.chat.id, msg.message_id)
        except:
            failures.append(cid)
    text = ("Часть не доставлено: " + ", ".join(map(str, failures))) if failures else "Рассылка успешно завершена."
    msg.reply_text(text + "\nНажмите /menu")
    context.user_data.pop("selected_chats", None)

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message), group=1)

# --- WEBHOOK ---
app = Flask(__name__)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK", 200
@app.route('/', methods=['GET'])
def index():
    return "OK"
if __name__ == '__main__':
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
