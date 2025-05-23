import os
import logging
import time
from flask import Flask, request
from telegram import (
    Update, Bot, ReplyKeyboardMarkup, InputMediaVideo, InputMediaVideoNote
)
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, Filters,
    CallbackContext, DispatcherHandlerStop
)
from telegram.utils.request import Request

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- Списки чатов ---
ALL_CITIES = [
    # ... (тот же список, что был у вас) ...
]
TEST_SEND_CHATS = [-1002596576819, -1002584369534]

# --- Права доступа ---
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

# --- Инициализация ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- /menu команда ---
def menu(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"], ["Тестовая отправка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    # Сброс состояния
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка меню ---
def handle_main_menu(update: Update, context: CallbackContext):
    if not context.user_data.pop("pending_main_menu", False):
        return
    text = update.message.text
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["mode"] = "broadcast"
        context.user_data["send_marker"] = update.message.message_id
        update.message.reply_text("Теперь отправьте ваши сообщения (кружки, текст и т.д.).", 
                                  disable_web_page_preview=True)
        raise DispatcherHandlerStop
    if text == "Тестовая отправка":
        context.user_data["mode"] = "test"
        context.user_data["test_marker"] = update.message.message_id
        update.message.reply_text("Тест: отправьте любые сообщения.", disable_web_page_preview=True)
        raise DispatcherHandlerStop
    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"] + [f"<a href='{c['link']}'>{c['name']}</a>" for c in ALL_CITIES]
        back = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True, reply_markup=back)
        raise DispatcherHandlerStop
    if text == "Назад":
        return menu(update, context)
    update.message.reply_text("Неверный выбор. /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- Буфер для медиа-групп ---
def init_media_buffer(context: CallbackContext):
    context.user_data["media_group_id"] = None
    context.user_data["media_buffer"] = []

# --- Функция отправки буфера ---
def flush_media_buffer(chat_list, context: CallbackContext, reply_to=None):
    buf = context.user_data.get("media_buffer", [])
    if not buf:
        return
    media_group_id = context.user_data.get("media_group_id")
    # Если в группе есть хотя бы два видео_note, используем send_media_group:
    media = []
    for msg in buf:
        if msg.video_note:
            media.append(InputMediaVideoNote(media=msg.video_note.file_id))
        elif msg.video:
            media.append(InputMediaVideo(media=msg.video.file_id, caption=msg.caption or ""))
    for cid in chat_list:
        try:
            if len(media) > 1:
                bot.send_media_group(chat_id=cid, media=media)
            else:
                # если один элемент — просто копируем
                bot.copy_message(cid, msg.chat.id, buf[0].message_id)
        except Exception as e:
            logging.error(f"Error sending media_group to {cid}: {e}")
    # очистка
    init_media_buffer(context)

# --- Пересылка сообщений и медиа (группы) ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    mode = context.user_data.get("mode")
    if not mode:
        return

    marker = context.user_data.get("test_marker") if mode=="test" else context.user_data.get("send_marker")
    if msg.message_id <= (marker or 0):
        return

    # Получаем список чатов
    chats = TEST_SEND_CHATS if mode=="test" else [c["chat_id"] for c in ALL_CITIES]

    mgid = msg.media_group_id
    # Если было ранее начало группы и сейчас другая или нет группы — сбросить
    if context.user_data.get("media_group_id") not in (mgid, None) and context.user_data.get("media_buffer"):
        flush_media_buffer(chats, context)

    # Если this message is part of group:
    if mgid:
        # Инициализация буфера, если новая группа
        if context.user_data.get("media_group_id") != mgid:
            init_media_buffer(context)
            context.user_data["media_group_id"] = mgid
        # добавляем в буфер
        context.user_data["media_buffer"].append(msg)
        # не слать сразу — дождёмся конца группы
        return

    # Если в буфере остались групповые сообщения, то шлём их перед текущим
    if context.user_data.get("media_buffer"):
        flush_media_buffer(chats, context)

    # Текст или одиночные медиа — просто копируем
    for cid in chats:
        try:
            if msg.text:
                bot.send_message(chat_id=cid,
                                 text=msg.text,
                                 entities=msg.entities or [],
                                 disable_web_page_preview=True)
            else:
                bot.copy_message(chat_id=cid,
                                 from_chat_id=msg.chat.id,
                                 message_id=msg.message_id)
        except Exception as e:
            logging.error(f"Error copying msg to {cid}: {e}")

    # в тестовом режиме после первого сообщения сбрасываем mode
    if mode=="test":
        context.user_data.pop("mode", None)
        update.message.reply_text("Тестовое сообщение отправлено.\n/menu")
    else:
        update.message.reply_text("Сообщение доставлено во все чаты.\n/menu")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document | Filters.video_note),
        forward_message
    ),
    group=1
)

# --- Flask-приложение и Webhook ---
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
