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

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая отправка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

def handle_main_menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS or not context.user_data.get("pending_main_menu"):
        return
    choice = update.message.text.strip()
    context.user_data.pop("pending_main_menu", None)
    if choice == "Тестовая отправка":
        context.user_data["bulk_messages"] = []
        context.user_data["pending_bulk"] = True
        update.message.reply_text(
            "Отправь сообщения (текст, фото, кружки и т.д.) для рассылки.\nКогда закончишь — напиши /sendall."
        )
        raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

def collect_bulk(update: Update, context: CallbackContext):
    if not context.user_data.get("pending_bulk"):
        return
    # Копируем всё, что пришло в bulk_messages
    context.user_data.setdefault("bulk_messages", []).append(update.message.message_id)
    update.message.reply_text(
        "Сообщение добавлено к рассылке. Когда закончите — напишите /sendall."
    )

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document | Filters.video_note),
        collect_bulk
    ),
    group=1
)

def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    msgs = context.user_data.get("bulk_messages", [])
    if not msgs:
        update.message.reply_text("Нет сообщений для рассылки.")
        return
    failed = []
    for mid in msgs:
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(
                    chat_id=cid,
                    from_chat_id=update.message.chat.id,
                    message_id=mid
                )
            except Exception as e:
                failed.append(cid)
                logging.error(f"Ошибка пересылки: {e}")
    if failed:
        update.message.reply_text("Не все сообщения ушли: " + ', '.join(map(str, failed)))
    else:
        update.message.reply_text("Рассылка завершена.")
    context.user_data["bulk_messages"] = []
    context.user_data["pending_bulk"] = False

dispatcher.add_handler(CommandHandler("sendall", sendall))

# --- Flask ---
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
