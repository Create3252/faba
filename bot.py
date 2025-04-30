import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup, MessageEntity
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    DispatcherHandlerStop
)
from telegram.utils.request import Request

# --- НАСТРОЙКА ЛОГОВ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# --- СПИСКИ ЧАТОВ ---
ALL_CITIES = [
    {"name": "Тюмень",        "date": "31.05.2024", "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy",  "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi",  "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi",  "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва",        "link": "https://t.me/+qokFNNnfhQdiYjQy",  "chat_id": -1002182445604},
    {"name": "Екатеринбург",  "link": "https://t.me/+J2ESyZJyOAk2YzYy",  "chat_id": -1002392430562},
    {"name": "Иркутск",       "link": "https://t.me/+TAoCnfoePUJmNzhi",  "chat_id": -1002255012184},
    {"name": "Оренбург",      "link": "https://t.me/+-Y_1N0HnePUxZjZi",  "chat_id": -1002316600732},
    {"name": "Крым",          "link": "https://t.me/+uC5IEnQWsmFhM2Ni",  "chat_id": -1002506541314},
    {"name": "Чита",          "link": "https://t.me/+yMeI0CjltLphZWYy",  "chat_id": -1002563254789},
    {"name": "Волгоград",     "link": "https://t.me/+ODxw0mfq73M4NGFi",  "chat_id": -1002562049204},
    {"name": "Краснодар",     "link": "https://t.me/+a9_1fWyGvAc1NzZi",  "chat_id": -1002297851122},
    {"name": "Пермь",         "link": "https://t.me/+lgM27u0cnp8wNjAy",  "chat_id": -1002298810010},
    {"name": "Самара",        "date": "15.04.2025", "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",   "link": "https://t.me/+Dpb3ozk_4Dc5OTYy",  "chat_id": -1002438533236},
    {"name": "Донецк",        "link": "https://t.me/+nGkS5gfvvQxjNmRi",  "chat_id": -1002328107804},
    {"name": "Хабаровск",     "link": "https://t.me/+SrnvRbMo3bA5NzVi",  "chat_id": -1002480768813},
    {"name": "Челябинск",     "link": "https://t.me/+ZKXj5rmcmMw0MzQy",  "chat_id": -1002374636424},
]
TEST_SEND_CHATS = [
    -1002596576819,
    -1002584369534
]

ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]
forwarded_messages = {}
city_lookup = {c["chat_id"]: c["name"] for c in ALL_CITIES}

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- ФОРМИРОВАНИЕ HTML-СООБЩЕНИЯ С ENTITIES ---
def rebuild_caption_with_entities(update: Update) -> str:
    text = update.message.caption or ""
    entities = update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        tag = {
            "bold": ("<b>", "</b>"),
            "italic": ("<i>", "</i>"),
            "underline": ("<u>", "</u>"),
            "strikethrough": ("<s>", "</s>"),
            "code": ("<code>", "</code>"),
            "spoiler": ("<u>", "</u>")
        }.get(ent.type, ("", ""))
        chars.insert(end, tag[1])
        chars.insert(start, tag[0])
    return "".join(chars)

# --- МЕНЮ ---
def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("Нет доступа")
    kb = [["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"], ["Тестовая отправка"]]
    update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА МЕНЮ ---
def handle_main_menu(update: Update, context: CallbackContext):
    if not context.user_data.pop("pending_main_menu", False):
        return
    text = update.message.text.strip()
    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"] + [
            f"<a href='{c['link']}'>{c['name']}</a>" if c.get("link") else c["name"]
            for c in ALL_CITIES
        ]
        update.message.reply_text("\n".join(lines),
                                  parse_mode="HTML",
                                  disable_web_page_preview=True,
                                  reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True))
        return DispatcherHandlerStop()
    if text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text("Теперь отправьте сообщение.\nНажмите /menu для перезапуска.")
        return DispatcherHandlerStop()
    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите текст/медиа для тестовой рассылки.")
        return DispatcherHandlerStop()
    if text == "Назад":
        return menu(update, context)

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu), group=0)

# --- ПЕРЕСЫЛКА МЕДИА В ХОДЕ forward_multimedia ---
def forward_multimedia(update: Update, chat_id):
    cap = rebuild_caption_with_entities(update)
    msg = update.message
    if msg.photo:
        return bot.send_photo(chat_id, msg.photo[-1].file_id, caption=cap, parse_mode="HTML")
    if msg.video:
        return bot.send_video(chat_id, msg.video.file_id, caption=cap, parse_mode="HTML")
    if msg.audio:
        return bot.send_audio(chat_id, msg.audio.file_id, caption=cap, parse_mode="HTML")
    if msg.document:
        return bot.send_document(chat_id, msg.document.file_id, caption=cap, parse_mode="HTML")
    return None

# --- ПЕРЕСЫЛКА СООБЩЕНИЙ КОПИРОВАНИЕМ ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    if msg.chat.type != "private":
        return

    # тестовая рассылка
    if context.user_data.pop("pending_test", False):
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except:
                failures.append(cid)
        text = ("Часть не дошла: " + ", ".join(map(str, failures))) if failures else "Тест успешно"
        return msg.reply_text(text + "\nНажмите /menu")

    # основная рассылка
    cids = context.user_data.pop("selected_chats", [])
    if not cids:
        return msg.reply_text("Сначала /menu")
    failures = []
    for cid in cids:
        try:
            bot.copy_message(cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        except:
            failures.append(cid)
    text = ("Часть не дошла: " + ", ".join(map(str, failures))) if failures else "Успешно"
    msg.reply_text(text + "\nНажмите /menu")

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message), group=1)

# --- Команды /edit, /delete, /getid опущены для краткости ---

# --- WEBHOOK ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK"

@app.route('/', methods=['GET'])
def index():
    return "OK"

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
