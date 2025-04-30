import os
import time
import logging
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    DispatcherHandlerStop
)
from telegram.utils.request import Request

# --- ЛОГИ ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- СПИСКИ ЧАТОВ ---
ALL_CITIES = [
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    # ... (остальные города) ...
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- Права ---
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]

# --- State storage ---
forwarded_messages = {}

# --- Инициализация бота и диспетчера ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- /menu ---
def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка меню (group=0) ---
def handle_main_menu(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS or not context.user_data.get("pending_main_menu"):
        return
    text = msg.text.strip()

    # «Назад» → просто показать меню снова
    if text == "Назад":
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop()  # отменяем все остальные хандлеры для этого update

    # Список чатов
    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for c in ALL_CITIES:
            lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
        msg.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        )
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop()

    # Рассылка по всем городам
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        context.user_data.pop("pending_main_menu", None)
        msg.reply_text("Теперь отправьте текст или медиа для рассылки.\nЧтобы отменить — /menu")
        raise DispatcherHandlerStop()

    # Тестовая отправка
    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        context.user_data.pop("pending_main_menu", None)
        msg.reply_text("Введите текст или медиа для тестовой отправки.\nЧтобы отменить — /menu")
        raise DispatcherHandlerStop()

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu),
    group=0
)

# --- Универсальная пересылка сообщений ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    # --- тестовая рассылка ---
    if context.user_data.pop("pending_test", False):
        fails = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(
                    chat_id=cid,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    disable_notification=False
                )
            except Exception:
                fails.append(cid)
        if fails:
            msg.reply_text(f"Не отправлено в: {','.join(map(str, fails))}\n/menu")
        else:
            msg.reply_text("Тест отправлен во все тестовые чаты.\n/menu")
        return

    # --- основная рассылка по выбранным чатам ---
    chat_ids = context.user_data.pop("selected_chats", [])
    if not chat_ids:
        return msg.reply_text("Сначала выберите действие — /menu")
    fails = []
    for cid in chat_ids:
        try:
            bot.copy_message(
                chat_id=cid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
        except Exception:
            fails.append(cid)
    if fails:
        msg.reply_text(f"Не доставлено в: {','.join(map(str, fails))}\n/menu")
    else:
        msg.reply_text("Доставлено во все чаты.\n/menu")

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message),
    group=1
)

# --- (ваши handlers для /edit, /delete, /getid) ---

# --- Flask + webhook ---
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
