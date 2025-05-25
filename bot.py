import os
import logging
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ALL_CITIES = [
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара",        "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",   "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",        "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",     "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
    {"name": "Тула",          "link": "https://t.me/+ZCq3GsGagIQ1NzRi", "chat_id": -1002678281080},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

user_buffers = {}
user_waiting = {}
user_mode = {}

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая рассылка"], ["Рассылка по городам"], ["Список чатов ФАБА"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)

def start_test_broadcast(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    user_buffers[uid] = []
    user_waiting[uid] = True
    user_mode[uid] = "test"
    update.message.reply_text("Отправляй любые сообщения (текст, фото, кружки и т.д.). Когда закончишь — напиши /sendall.")

def start_city_broadcast(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    user_buffers[uid] = []
    user_waiting[uid] = True
    user_mode[uid] = "city"
    update.message.reply_text("Отправляй любые сообщения для рассылки по всем городам. Когда закончишь — напиши /sendall.")

def send_chat_list(update: Update, context: CallbackContext):
    lines = ["Список чатов ФАБА:"]
    for city in ALL_CITIES:
        lines.append(f"<a href='{city['link']}'>{city['name']}</a>")
    update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

def add_to_buffer(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if not user_waiting.get(uid):
        return
    if update.message.text and update.message.text.startswith("/"):
        return
    user_buffers.setdefault(uid, []).append(update.message)
    if len(user_buffers[uid]) == 1:
        update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")

def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if not user_buffers.get(uid):
        update.message.reply_text("Нет сообщений для рассылки.")
        return
    # Куда рассылать?
    if user_mode.get(uid) == "city":
        chat_ids = [c["chat_id"] for c in ALL_CITIES]
    else:
        chat_ids = TEST_SEND_CHATS
    for msg in user_buffers[uid]:
        for chat_id in chat_ids:
            try:
                bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка при пересылке: {e}")
    update.message.reply_text("Рассылка завершена.")
    user_buffers[uid] = []
    user_waiting[uid] = False
    user_mode[uid] = None

dispatcher.add_handler(CommandHandler("menu", menu))
dispatcher.add_handler(MessageHandler(Filters.regex("^Тестовая рассылка$"), start_test_broadcast))
dispatcher.add_handler(MessageHandler(Filters.regex("^Рассылка по городам$"), start_city_broadcast))
dispatcher.add_handler(MessageHandler(Filters.regex("^Список чатов ФАБА$"), send_chat_list))
dispatcher.add_handler(CommandHandler("sendall", sendall))
dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & ~Filters.command,
        add_to_buffer
    )
)

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
