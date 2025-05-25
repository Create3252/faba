import os
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ALL_CITIES = [{"name": "Тест", "chat_id": -1001234567890}]
ALLOWED_USER_IDS = {296920330}

req = None
bot = None
dispatcher = None

user_queues = {}

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Бот готов. Пиши сообщения для рассылки. /sendall чтобы разослать.")

def add_to_queue(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    q = user_queues.setdefault(uid, [])
    q.append(update.message)
    update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")

def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    queue = user_queues.get(uid, [])
    errors = []
    for msg in queue:
        for city in ALL_CITIES:
            try:
                bot.copy_message(city["chat_id"], msg.chat.id, msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка отправки: {e}")
                errors.append(city["name"])
    user_queues[uid] = []
    update.message.reply_text("Рассылка завершена." if not errors else f"Ошибки: {errors}")

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

def setup():
    global req, bot, dispatcher
    from telegram.utils.request import Request
    req = Request()
    bot = Bot(token=BOT_TOKEN, request=req)
    dispatcher = Dispatcher(bot, None, workers=4)
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("sendall", sendall))
    dispatcher.add_handler(MessageHandler(Filters.chat_type.private, add_to_queue))

setup()

if __name__ == '__main__':
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
