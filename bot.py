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
    DispatcherHandlerStop
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

# --- Настройка чатов ---
ALL_CITIES = [
    {"name": "Тюмень",      "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск","link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",    "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    # ... остальные города ...
    {"name": "Челябинск",  "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

# --- Инициализация бота и диспетчера ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- Буфер для любых медиа ---
def init_media_buffer(context: CallbackContext):
    context.user_data["media_buffer"] = []

def flush_media_buffer(chats, context: CallbackContext):
    buf = context.user_data.get("media_buffer", [])
    for msg in buf:
        for cid in chats:
            try:
                bot.copy_message(chat_id=cid,
                                 from_chat_id=msg.chat.id,
                                 message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка копирования медиа в {cid}: {e}")
    init_media_buffer(context)

# --- /menu ---
def menu(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка меню ---
def handle_main_menu(update: Update, context: CallbackContext):
    if not context.user_data.pop("pending_main_menu", False):
        return
    choice = update.message.text.strip()
    if choice == "Отправить сообщение во все чаты ФАБА":
        context.user_data["mode"] = "broadcast"
        context.user_data["marker"] = update.message.message_id
        init_media_buffer(context)
        update.message.reply_text(
            "Теперь отправьте ваши сообщения (кружки, текст, видео…)\n/menu для отмены",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

    if choice == "Тестовая отправка":
        context.user_data["mode"] = "test"
        context.user_data["marker"] = update.message.message_id
        init_media_buffer(context)
        update.message.reply_text(
            "Тест: отправьте любой контент\n/menu для отмены",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

    if choice == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"] + [
            f"<a href='{c['link']}'>{c['name']}</a>"
            for c in ALL_CITIES
        ]
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        )
        raise DispatcherHandlerStop

    if choice == "Назад":
        return menu(update, context)

    update.message.reply_text("Неверный выбор. /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- Пересылка сообщений и медиа ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    mode = context.user_data.get("mode")
    if not mode:
        return

    marker = context.user_data.get("marker", 0)
    if msg.message_id <= marker:
        return

    # Куда шлём
    chats = TEST_SEND_CHATS if mode == "test" else [c["chat_id"] for c in ALL_CITIES]

    # Если это любое медиа (включая video_note) — буферизуем
    is_media = any([
        msg.photo, msg.video, msg.audio, msg.document, getattr(msg, "video_note", None)
    ])
    if is_media:
        context.user_data["media_buffer"].append(msg)
        return

    # А вот текст или кнопка «Назад» — сначала сбросим буфер
    if context.user_data.get("media_buffer"):
        flush_media_buffer(chats, context)

    # Затем сам текст
    text = msg.text or ""
    for cid in chats:
        try:
            bot.send_message(
                chat_id=cid,
                text=text,
                entities=msg.entities or [],
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.error(f"Ошибка отправки текста в {cid}: {e}")

    # Итоговый ответ пользователю
    context.user_data.pop("mode", None)
    update.message.reply_text(
        "Сообщение доставлено во все чаты!\n/menu"
        if mode=="broadcast"
        else "Тестовое сообщение отправлено.\n/menu"
    )

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video |
            Filters.audio | Filters.document | Filters.video_note
        ),
        forward_message
    ),
    group=1
)

# --- Flask/Webhook ---
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
