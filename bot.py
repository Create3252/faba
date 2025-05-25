import os
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

TEST_SEND_CHATS = [
    -1002596576819,
    -1002584369534
]
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- Flask-приложение и webhook ---
app = Flask(__name__)

# --- Сборщик рассылки ---
def add_to_broadcast(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    queue = context.user_data.setdefault("pending_broadcast", [])
    # Сохраняем все сообщения как объекты Message
    queue.append(update.message)
    update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video | Filters.video_note | Filters.audio | Filters.document
        ),
        add_to_broadcast
    ),
    group=0
)

# --- Команда sendall ---
def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    queue = context.user_data.get("pending_broadcast", [])
    if not queue:
        update.message.reply_text("Нет сообщений для рассылки. Сначала отправьте сообщения.")
        return
    failures = []
    for msg in queue:
        for cid in TEST_SEND_CHATS:
            try:
                # Универсально пересылаем всё через copy_message
                bot.copy_message(
                    chat_id=cid,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
            except Exception as e:
                failures.append(cid)
                logging.error(f"Не удалось отправить сообщение в {cid}: {e}")
    context.user_data["pending_broadcast"] = []
    if failures:
        update.message.reply_text(f"Не отправлено в: {', '.join(map(str, failures))}")
    else:
        update.message.reply_text("Все сообщения отправлены во все тестовые чаты.")

dispatcher.add_handler(CommandHandler("sendall", sendall))

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
