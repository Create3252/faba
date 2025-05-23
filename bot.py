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
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUjmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара",        "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",   "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",        "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",     "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
    {"name": "Тула",          "link": "https://t.me/+ZCq3GsGagIQ1NzRi", "chat_id": -1002678281080},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- Права доступа ---
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

# --- Инициализация бота и диспетчера ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- /menu команда ---
def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"], ["Тестовая отправка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка меню ---
def handle_main_menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS or not context.user_data.get("pending_main_menu"):
        return
    choice = update.message.text.strip()
    context.user_data.pop("pending_main_menu", None)
    # Сохраним ID маркера, чтобы не пересылать его как контент
    context.user_data["marker_id"] = update.message.message_id

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

    if choice == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        context.user_data["send_marker"] = update.message.message_id
        update.message.reply_text(
            "Теперь отправьте ваше сообщение (текст или медиа).\nЧтобы отменить — /menu",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

    if choice == "Тестовая отправка":
        context.user_data["pending_test"] = True
        context.user_data["test_marker"] = update.message.message_id
        update.message.reply_text(
            "Ввод тестового сообщения (текст или медиа).\nЧтобы отменить — /menu",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop

    if choice == "Назад":
        return menu(update, context)

    update.message.reply_text("Неверный выбор, /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- Пересылка текстов и медиа (включая video_note) ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    mid = msg.message_id
    # Не пересылаем маркеры меню или теста
    if mid in {context.user_data.get("marker_id"),
               context.user_data.get("send_marker"),
               context.user_data.get("test_marker")}:
        return

    # 1) Тестовая отправка?
    if context.user_data.pop("pending_test", False):
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                if msg.text and msg.entities:
                    bot.send_message(
                        chat_id=cid,
                        text=msg.text,
                        entities=msg.entities,
                        disable_web_page_preview=True
                    )
                else:
                    bot.copy_message(
                        chat_id=cid,
                        from_chat_id=msg.chat.id,
                        message_id=mid
                    )
                logging.info(f"[TEST] → {cid}")
            except Exception as e:
                logging.error(f"[TEST] error {cid}: {e}")
                failures.append(cid)
        reply = "Не удалось в: " + ", ".join(map(str, failures)) if failures else "Тестовое сообщение отправлено."
        msg.reply_text(reply)
        msg.reply_text("Нажмите /menu для нового выбора.")
        return

    # 2) Основная рассылка?
    if "selected_chats" in context.user_data:
        chat_ids = context.user_data["selected_chats"]
        failures = []
        for cid in chat_ids:
            try:
                if msg.text and msg.entities:
                    bot.send_message(
                        chat_id=cid,
                        text=msg.text,
                        entities=msg.entities,
                        disable_web_page_preview=True
                    )
                else:
                    bot.copy_message(
                        chat_id=cid,
                        from_chat_id=msg.chat.id,
                        message_id=mid
                    )
                logging.info(f"[SEND] → {cid}")
            except Exception as e:
                logging.error(f"[SEND] error {cid}: {e}")
                failures.append(cid)
        reply = "Не отправлено в: " + ", ".join(map(str, failures)) if failures else "Сообщение доставлено во все чаты."
        msg.reply_text(reply)
        msg.reply_text("Нажмите /menu для нового выбора.")
        # НЕ очищаем selected_chats — чтобы пересылать сколько угодно сообщений подряд
        return

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
