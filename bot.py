import os
import logging
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from telegram.utils.request import Request

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# Глобальное хранилище очереди рассылки (user_id -> [msg])
pending_messages = {}

def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая рассылка"], ["/sendall"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)

dispatcher.add_handler(CommandHandler("menu", menu))

def start_sending(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    pending_messages[uid] = []
    update.message.reply_text("Отправляй любые сообщения (текст, фото, кружки и т.д.). Когда закончишь — напиши /sendall.")

dispatcher.add_handler(MessageHandler(Filters.regex("^Тестовая рассылка$"), start_sending), group=0)

def collect_message(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    # только если уже запущена рассылка (иначе игнор)
    if uid not in pending_messages:
        return

    # сохраняем update.message в очередь (копию!)
    pending_messages[uid].append(update.message)
    update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")
    logging.info(f"Добавлено сообщение id={update.message.message_id} от {uid} в очередь рассылки.")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.video_note | Filters.audio | Filters.document | Filters.sticker),
        collect_message
    ),
    group=1
)

def send_all(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    msgs = pending_messages.pop(uid, [])
    if not msgs:
        update.message.reply_text("Нет сообщений для рассылки.")
        return

    for m in msgs:
        for cid in TEST_SEND_CHATS:
            try:
                # Отправляем по типу
                if m.text and not m.photo and not m.video and not m.video_note and not m.audio and not m.document and not m.sticker:
                    bot.send_message(chat_id=cid, text=m.text, entities=m.entities, disable_web_page_preview=True)
                    logging.info(f"Отправлен текст id={m.message_id} -> чат {cid}")
                elif m.photo:
                    bot.send_photo(chat_id=cid, photo=m.photo[-1].file_id, caption=m.caption or None, caption_entities=m.caption_entities)
                    logging.info(f"Отправлено фото id={m.message_id} -> чат {cid}")
                elif m.video:
                    bot.send_video(chat_id=cid, video=m.video.file_id, caption=m.caption or None, caption_entities=m.caption_entities)
                    logging.info(f"Отправлено видео id={m.message_id} -> чат {cid}")
                elif m.video_note:
                    bot.send_video_note(chat_id=cid, video_note=m.video_note.file_id, length=m.video_note.length, duration=m.video_note.duration)
                    logging.info(f"Отправлен кружок id={m.message_id} -> чат {cid}")
                elif m.audio:
                    bot.send_audio(chat_id=cid, audio=m.audio.file_id, caption=m.caption or None, caption_entities=m.caption_entities)
                    logging.info(f"Отправлено аудио id={m.message_id} -> чат {cid}")
                elif m.document:
                    bot.send_document(chat_id=cid, document=m.document.file_id, caption=m.caption or None, caption_entities=m.caption_entities)
                    logging.info(f"Отправлен документ id={m.message_id} -> чат {cid}")
                elif m.sticker:
                    bot.send_sticker(chat_id=cid, sticker=m.sticker.file_id)
                    logging.info(f"Отправлен стикер id={m.message_id} -> чат {cid}")
            except Exception as e:
                logging.error(f"Ошибка отправки id={m.message_id} в {cid}: {e}")

    update.message.reply_text("Все сообщения отправлены.")
    logging.info(f"Рассылка завершена для пользователя {uid}.")

dispatcher.add_handler(CommandHandler("sendall", send_all), group=2)

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
