import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.utils.request import Request

# --- ЛОГИ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например "https://your-app.onrender.com"
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Нужно задать BOT_TOKEN и WEBHOOK_URL")

# --- ГОРОДА И ТЕСТОВЫЕ ЧАТЫ ---
ALL_CITIES = [
    {"name": "Тюмень",         "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",    "link": "https://t.me/+wx20YVCwxmo3YmQy",  "chat_id": -1002489311984},
    {"name": "Сахалин",        "link": "https://t.me/+FzQ_jEYX8AtkMzNi",  "chat_id": -1002265902434},
    {"name": "Красноярск",     "link": "https://t.me/+lMTDVPF0syRiYzdi",  "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",         "link": "https://t.me/+qokFNNnfhQdiYjQy",  "chat_id": -1002182445604},
    {"name": "Екатеринбург",   "link": "https://t.me/+J2ESyZJyOAk2YzYy",  "chat_id": -1002392430562},
    {"name": "Иркутск",        "link": "https://t.me/+TAoCnfoePUJmNzhi",  "chat_id": -1002255012184},
    {"name": "Оренбург",       "link": "https://t.me/+-Y_1N0HnePUxZjZi",  "chat_id": -1002316600732},
    {"name": "Крым",           "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",           "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",      "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",      "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",          "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",         "link": "https://t.me/+SLCllcYKCUFlNjk6","chat_id": -1002589409715},
    {"name": "Владивосток",    "link": "https://t.me/+Dpb3ozk_4Dc5OTYy","chat_id": -1002438533236},
    {"name": "Донецк",         "link": "https://t.me/+nGkS5gfvvQxjNmRi","chat_id": -1002328107804},
    {"name": "Хабаровск",      "link": "https://t.me/+SrnvRbMo3bA5NzVi","chat_id": -1002480768813},
    {"name": "Челябинск",      "link": "https://t.me/+ZKXj5rmcmMw0MzQy","chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 1283190854, 1607945564]

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
app = ApplicationBuilder().bot(bot).build()

# хранение пересланных сообщений для /edit и /delete (если нужно)
forwarded_messages = {}

# --- /menu ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        return await update.message.reply_text("❌ У вас нет прав для использования бота.")
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    kb = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=kb)
    context.user_data["pending_menu"] = True

app.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА ВЫБОРА ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.pop("pending_menu", False):
        return
    text = update.message.text

    if text == "Список чатов ФАБА":
        lines = ["<b>Список чатов ФАБА:</b>"]
        for city in ALL_CITIES:
            lines.append(f"<a href='{city['link']}'>{city['name']}</a>")
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return

    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["to_chats"] = [c["chat_id"] for c in ALL_CITIES]
        return await update.message.reply_text(
            "Теперь отправьте сообщение для рассылки.\nНажмите /menu для отмены."
        )

    if text == "Тестовая отправка":
        context.user_data["test_send"] = True
        return await update.message.reply_text(
            "Введите текст или отправьте медиа для тестовой отправки.\nНажмите /menu для отмены."
        )

    await update.message.reply_text("Неверный выбор. Используйте /menu для повторного выбора.")

app.add_handler(MessageHandler(
    filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
    handle_menu
))

# --- ПЕРЕСЫЛКА И ТЕСТ ---
async def forward_any(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type != "private":
        return

    # Тестовая отправка
    if context.user_data.pop("test_send", False):
        for cid in TEST_SEND_CHATS:
            await bot.copy_message(
                chat_id=cid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
        return await msg.reply_text("✅ Тестовое сообщение отправлено.")

    # Рассылка по выбранным чатам
    chat_ids = context.user_data.pop("to_chats", None)
    if chat_ids:
        for cid in chat_ids:
            await bot.copy_message(
                chat_id=cid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
        return await msg.reply_text("✅ Сообщение отправлено во все чаты.")

app.add_handler(MessageHandler(
    filters.ChatType.PRIVATE & ~filters.COMMAND,
    forward_any
))

# --- ВЕБХУК СЕРВЕР ---
flask_app = Flask(__name__)

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    app.process_update(update)
    return "OK"

@flask_app.route("/ping", methods=["GET"])
def ping():
    return "pong"

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is running"

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    port = int(os.getenv("PORT", 5000))
    logging.info(f"Запуск Flask на порту {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
