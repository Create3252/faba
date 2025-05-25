import os
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    DispatcherHandlerStop,
)
from telegram.utils.request import Request

# --- Логи ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

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

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Список чатов ФАБА", "Тестовая рассылка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()  # Сбросить все состояния

dispatcher.add_handler(CommandHandler("menu", menu))

def handle_main_menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    choice = update.message.text.strip()
    if choice == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"] + [
            f"<a href='{c['link']}'>{c['name']}</a>" for c in ALL_CITIES
        ]
        back = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=back
        )
        raise DispatcherHandlerStop

    if choice == "Тестовая рассылка":
        context.user_data["collecting_broadcast"] = True
        context.user_data["broadcast_messages"] = []
        update.message.reply_text(
            "Отправляй любые сообщения (текст, фото, кружки и т.д.). Когда закончишь — напиши /sendall."
        )
        raise DispatcherHandlerStop

    if choice == "Назад":
        return menu(update, context)

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

def collect_broadcast(update: Update, context: CallbackContext):
    user_data = context.user_data
    if user_data.get("collecting_broadcast"):
        # Добавляем id сообщений к рассылке
        user_data.setdefault("broadcast_messages", []).append(update.message.message_id)
        if not user_data.get("notified"):
            update.message.reply_text(
                "Сообщение добавлено к рассылке. Когда закончите — напишите /sendall."
            )
            user_data["notified"] = True
        else:
            # Не спамим уведомлением повторно
            pass
        raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document | Filters.voice | Filters.video_note
        ),
        collect_broadcast
    ),
    group=1
)

def sendall(update: Update, context: CallbackContext):
    user_data = context.user_data
    if not user_data.get("collecting_broadcast") or not user_data.get("broadcast_messages"):
        update.message.reply_text("Нет сообщений для рассылки.")
        return

    failures = []
    sent = 0
    for mid in user_data["broadcast_messages"]:
        try:
            # Пересылаем в каждый тестовый чат
            for cid in TEST_SEND_CHATS:
                bot.copy_message(chat_id=cid, from_chat_id=update.message.chat.id, message_id=mid)
            sent += 1
        except Exception as e:
            failures.append(str(mid))
            logging.error(f"Не удалось отправить {mid}: {e}")
    update.message.reply_text(f"Рассылка завершена. Отправлено: {sent}.")
    if failures:
        update.message.reply_text(f"Не удалось отправить: {', '.join(failures)}.")
    # Очистить состояние
    context.user_data.clear()

dispatcher.add_handler(CommandHandler("sendall", sendall))

# Flask & Webhook
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
