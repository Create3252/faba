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

# --- Списки чатов ---
ALL_CITIES = [
    {"name": "Тюмень",      "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск", "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",     "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",  "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "СПб",         "link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва",      "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург","link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",     "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",    "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",        "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002506541314},
    {"name": "Чита",        "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград",   "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар",   "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь",       "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара",      "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток", "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",      "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",   "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",   "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- Права доступа ---
ALLOWED_USER_IDS = {
    296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564
}

# --- Инициализация бота и диспетчера ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- Вспомогательные функции для буфера медиа-группы ---
def init_media_buffer(context: CallbackContext):
    context.user_data["media_group_id"] = None
    context.user_data["media_buffer"] = []

def flush_media_buffer(chat_list, context: CallbackContext):
    buf = context.user_data.get("media_buffer", [])
    if not buf:
        return
    for msg in buf:
        for cid in chat_list:
            try:
                bot.copy_message(chat_id=cid,
                                 from_chat_id=msg.chat.id,
                                 message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка при копировании media_group в {cid}: {e}")
    init_media_buffer(context)

# --- /menu команда ---
def menu(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка выбора в меню ---
def handle_main_menu(update: Update, context: CallbackContext):
    if not context.user_data.pop("pending_main_menu", False):
        return
    choice = update.message.text.strip()
    if choice == "Отправить сообщение во все чаты ФАБА":
        context.user_data["mode"] = "broadcast"
        context.user_data["send_marker"] = update.message.message_id
        init_media_buffer(context)
        update.message.reply_text(
            "Теперь отправьте свои сообщения (кружки, видео, текст и т.д.).",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

    if choice == "Тестовая отправка":
        context.user_data["mode"] = "test"
        context.user_data["test_marker"] = update.message.message_id
        init_media_buffer(context)
        update.message.reply_text(
            "Тест: отправьте любое сообщение (текст или медиа).",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

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

    if choice == "Назад":
        return menu(update, context)

    update.message.reply_text("Неверный выбор. /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- Основной хэндлер пересылки (текст, медиа, video_note, группы) ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    mode = context.user_data.get("mode")
    if not mode:
        return

    # Определяем маркер (чтобы не копировать служебные меню-сообщения)
    marker = context.user_data.get("test_marker") if mode == "test" else context.user_data.get("send_marker")
    if msg.message_id <= (marker or 0):
        return

    # Выбираем, куда шлём
    chats = TEST_SEND_CHATS if mode == "test" else [c["chat_id"] for c in ALL_CITIES]

    # Обработка media_group
    mgid = msg.media_group_id
    # Если начался новый media_group или buffer ещё не пуст — сбросим старый
    if context.user_data.get("media_group_id") not in (mgid, None) and context.user_data.get("media_buffer"):
        flush_media_buffer(chats, context)

    if mgid:
        # Начинаем новую группу
        if context.user_data.get("media_group_id") != mgid:
            init_media_buffer(context)
            context.user_data["media_group_id"] = mgid
        # Буферизуем
        context.user_data["media_buffer"].append(msg)
        return

    # Если остались в буфере сообщения группы — шлём их
    if context.user_data.get("media_buffer"):
        flush_media_buffer(chats, context)

    # Одиночное сообщение (текст или медиа без группы) — копируем
    for cid in chats:
        try:
            if msg.text:
                bot.send_message(
                    chat_id=cid,
                    text=msg.text,
                    entities=msg.entities or [],
                    disable_web_page_preview=True
                )
            else:
                bot.copy_message(
                    chat_id=cid,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
        except Exception as e:
            logging.error(f"Ошибка при пересылке в {cid}: {e}")

    # Ответ пользователю
    if mode == "test":
        context.user_data.pop("mode", None)
        update.message.reply_text("Тестовое сообщение отправлено.\n/menu")
    else:
        update.message.reply_text("Сообщение доставлено во все чаты.\n/menu")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video | Filters.audio |
            Filters.document | Filters.video_note
        ),
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
