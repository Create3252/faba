import os
import logging
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TEST_SEND_CHATS = [-1002596576819, -1002584369534]
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- Глобальный буфер сообщений по user_id
user_buffers = {}

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая рассылка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)

def start_test_broadcast(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    user_buffers[uid] = []
    update.message.reply_text(
        "Отправляй любые сообщения (текст, фото, кружки и т.д.). Когда закончишь — напиши /sendall."
    )

def add_to_buffer(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in user_buffers:
        return
    user_buffers[uid].append(update.message)
    update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")

def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in user_buffers or not user_buffers[uid]:
        update.message.reply_text("Нет сообщений для рассылки.")
        return
    for msg in user_buffers[uid]:
        for chat_id in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка при пересылке: {e}")
    update.message.reply_text("Рассылка завершена.")
    user_buffers[uid] = []

dispatcher.add_handler(CommandHandler("menu", menu))
dispatcher.add_handler(MessageHandler(Filters.regex("^Тестовая рассылка$"), start_test_broadcast))
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
