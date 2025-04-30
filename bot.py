import os
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, Filters,
    CallbackContext, DispatcherHandlerStop
)
from telegram.utils.request import Request

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- ПАРАМЕТРЫ ОКРУЖЕНИЯ ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- СПИСОК ЧАТОВ ---
ALL_CITIES = [
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",        "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",   "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",        "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",     "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- ДОСТУП ---
ALLOWED_USER_IDS = [
    296920330, 320303183, 533773,
    327650534, 533007308, 136737738, 1607945564
]

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
req        = Request(connect_timeout=20, read_timeout=20)
bot        = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)
app        = Flask(__name__)

# --- КНОПКА /menu ---
def menu(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    context.user_data.clear()
    kb = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА НАЖАТИЙ МЕНЮ ---
def handle_choice(update: Update, context: CallbackContext):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if uid not in ALLOWED_USER_IDS:
        return
    # только эти четыре — дальше не уходим в forward_all
    if text not in ("Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА", "Тестовая отправка", "Назад"):
        return

    # 1) Показать список
    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for c in ALL_CITIES:
            lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
        back = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=back
        )
        raise DispatcherHandlerStop()

    # 2) Рассылка во все чаты
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text(
            "Теперь отправьте ваше сообщение (текст или медиа).\nНажмите /menu для отмены.",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop()

    # 3) Тестовая отправка
    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text(
            "Введите текст или медиа для тестовой отправки.\nНажмите /menu для отмены.",
            disable_web_page_preview=True
        )
        raise DispatcherHandlerStop()

    # 4) Назад — просто переоткрываем меню
    if text == "Назад":
        menu(update, context)
        raise DispatcherHandlerStop()

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        Filters.regex("^(Список чатов ФАБА|Отправить сообщение во все чаты ФАБА|Тестовая отправка|Назад)$"),
        handle_choice
    ),
    group=0
)

# --- УНИВЕРСАЛЬНАЯ ПЕРЕСЫЛКА / TEST ---
def forward_all(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    # Игнорируем меню-тексты, они уже обработаны
    if msg.text and msg.text in ("Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА", "Тестовая отправка", "Назад"):
        return

    # 1) Тестовая рассылка?
    if context.user_data.pop("pending_test", False):
        fails = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception:
                fails.append(str(cid))
        reply = (
            f"Не удалось в: {', '.join(fails)}"
            if fails else
            "Тестовое сообщение отправлено."
        )
        update.message.reply_text(reply)
        return update.message.reply_text("Нажмите /menu для нового выбора.")

    # 2) Основная рассылка?
    chats = context.user_data.pop("selected_chats", None)
    if chats:
        fails = []
        for cid in chats:
            try:
                # если в тексте есть хотя бы одна ссылка (url или text_link)
                if msg.text and msg.entities and any(e.type in ("url", "text_link") for e in msg.entities):
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
                        message_id=msg.message_id
                    )
            except Exception:
                fails.append(str(cid))
        reply = (
            f"Не доставлено в: {', '.join(fails)}"
            if fails else
            "Сообщение доставлено во все чаты."
        )
        update.message.reply_text(reply)
        return update.message.reply_text("Нажмите /menu для нового выбора.")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document),
        forward_all
    ),
    group=1
)

# --- WEBHOOK ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    upd  = Update.de_json(data, bot)
    dispatcher.process_update(upd)
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
