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

# Тестовые чаты
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

# Очередь сообщений пользователя для рассылки
user_message_queues = {}

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая рассылка"], ["Очистить очередь"]]
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
    if choice == "Тестовая рассылка":
        context.user_data["collect_broadcast"] = True
        user_message_queues[uid] = []
        update.message.reply_text(
            "Отправь одно или несколько сообщений (текст, медиа, кружки и т.д.).\nКогда закончишь — напиши /sendall",
        )
        raise DispatcherHandlerStop
    if choice == "Очистить очередь":
        user_message_queues[uid] = []
        update.message.reply_text("Очередь очищена.")
        raise DispatcherHandlerStop

    update.message.reply_text("Неверный выбор. /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

def collect_messages(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if context.user_data.get("collect_broadcast"):
        if uid not in user_message_queues:
            user_message_queues[uid] = []
        user_message_queues[uid].append(update.message)
        update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")
        raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document | Filters.video_note),
        collect_messages
    ),
    group=1
)

def sendall(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    queue = user_message_queues.get(uid, [])
    if not queue:
        update.message.reply_text("Нет сообщений для отправки.")
        return

    failures = []
    for msg in queue:
        for chat_id in TEST_SEND_CHATS:
            try:
                if msg.text and not (msg.photo or msg.video or msg.audio or msg.document or msg.video_note):
                    bot.send_message(chat_id=chat_id, text=msg.text, entities=msg.entities, disable_web_page_preview=True)
                elif msg.photo:
                    bot.send_photo(chat_id=chat_id, photo=msg.photo[-1].file_id, caption=msg.caption, caption_entities=msg.caption_entities)
                elif msg.video:
                    bot.send_video(chat_id=chat_id, video=msg.video.file_id, caption=msg.caption, caption_entities=msg.caption_entities)
                elif msg.audio:
                    bot.send_audio(chat_id=chat_id, audio=msg.audio.file_id, caption=msg.caption, caption_entities=msg.caption_entities)
                elif msg.document:
                    bot.send_document(chat_id=chat_id, document=msg.document.file_id, caption=msg.caption, caption_entities=msg.caption_entities)
                elif msg.video_note:
                    bot.send_video_note(chat_id=chat_id, video_note=msg.video_note.file_id)
                else:
                    bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка отправки: {e}")
                failures.append(chat_id)
    user_message_queues[uid] = []
    context.user_data["collect_broadcast"] = False
    if failures:
        update.message.reply_text(f"Ошибка в: {', '.join(map(str, failures))}")
    else:
        update.message.reply_text("Все сообщения отправлены в тестовые чаты.")

dispatcher.add_handler(CommandHandler("sendall", sendall))

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
