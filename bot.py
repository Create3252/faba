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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# --- СПИСКИ ГОРОДОВ И ТЕСТОВЫХ ЧАТОВ ---
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
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]
forwarded_messages = {}

# Создаём бота и диспетчер
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- ВСПОМОГАТЕЛЬ: перестраиваем caption с HTML-entities ---
def rebuild_caption_with_entities(update: Update) -> str:
    if not update.message.caption:
        return ""
    text = update.message.caption
    ents = update.message.caption_entities or []
    chars = list(text)
    for e in sorted(ents, key=lambda x: x.offset + x.length, reverse=True):
        start, end = e.offset, e.offset + e.length
        tag = {
            "bold": ("<b>","</b>"),
            "italic": ("<i>","</i>"),
            "underline": ("<u>","</u>"),
            "strikethrough": ("<s>","</s>"),
            "code": ("<code>","</code>"),
            # для spoiler ❗️ HTML-спойлера нет — используем подчёркивание
            "spoiler": ("<u>","</u>")
        }.get(e.type)
        if tag:
            chars.insert(end, tag[1])
            chars.insert(start, tag[0])
    return "".join(chars)

# --- ОТПРАВКА ТЕКСТА (с сохранением entities + без предпросмотра) ---
def forward_text(msg, chat_id):
    try:
        bot.send_message(
            chat_id=chat_id,
            text=msg.text or msg.caption or "",
            entities=msg.entities or msg.caption_entities,
            disable_web_page_preview=True
        )
        logging.info(f"Отправлен текст → {chat_id}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при send_message в {chat_id}: {e}")
        return False

# --- ОТПРАВКА МЕДИА ---
def forward_multimedia(update: Update, chat_id):
    new_caption = rebuild_caption_with_entities(update)
    m = update.message
    try:
        if m.photo:
            bot.send_photo(chat_id=chat_id, photo=m.photo[-1].file_id,
                           caption=new_caption, parse_mode="HTML")
        elif m.video:
            bot.send_video(chat_id=chat_id, video=m.video.file_id,
                           caption=new_caption, parse_mode="HTML")
        elif m.audio:
            bot.send_audio(chat_id=chat_id, audio=m.audio.file_id,
                           caption=new_caption, parse_mode="HTML")
        elif m.document:
            bot.send_document(chat_id=chat_id, document=m.document.file_id,
                              caption=new_caption, parse_mode="HTML")
        else:
            # если вдруг не узнали медиа — как текст
            return forward_text(m, chat_id)
        logging.info(f"Отправлено медиа → {chat_id}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при send_media в {chat_id}: {e}")
        return False

# --- /menu ---
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return update.message.reply_text("Нет доступа.")
    kb = [["Список чатов ФАБА","Отправить сообщение во все чаты ФАБА"],
          ["Тестовая отправка"]]
    update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА МЕНЮ (group=0) ---
def handle_main_menu(update: Update, context: CallbackContext):
    u = update.message
    if u.from_user.id not in ALLOWED_USER_IDS or "pending_main_menu" not in context.user_data:
        return
    text = u.text.strip()
    if text == "Назад":
        return menu(update, context)
    if text == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for c in ALL_CITIES:
            if c.get("link"):
                lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
            else:
                lines.append(c["name"])
        update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        )
    elif text == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        update.message.reply_text("Теперь отправьте текст или медиа для рассылки.\nНажмите /menu для отмены.")
    elif text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите текст или медиа для тестовой отправки.\nНажмите /menu для отмены.")
    else:
        update.message.reply_text("Неверный выбор. /menu")
    context.user_data.pop("pending_main_menu", None)

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu), group=0)

# --- ПЕРЕСЫЛКА (group=1) ---
def forward_message(update: Update, context: CallbackContext):
    m = update.message
    if m.from_user.id not in ALLOWED_USER_IDS:
        return
    # тестовая
    if context.user_data.pop("pending_test", False):
        failures = []
        for cid in TEST_SEND_CHATS:
            ok = forward_multimedia(update, cid) if (m.photo or m.video or m.audio or m.document) else forward_text(m, cid)
            if not ok: failures.append(cid)
        if failures:
            m.reply_text(f"Не отправлено в: {','.join(str(x) for x in failures)}\n/menu")
        else:
            m.reply_text("Тестовое сообщение отправлено во все тестовые чаты.\n/menu")
        return

    # обычная
    chat_ids = context.user_data.pop("selected_chats", [])
    if not chat_ids:
        return m.reply_text("Сначала /menu")
    failures = []
    for cid in chat_ids:
        ok = forward_multimedia(update, cid) if (m.photo or m.video or m.audio or m.document) else forward_text(m, cid)
        if not ok: failures.append(cid)
    if failures:
        m.reply_text(f"Не отправлено в: {','.join(str(x) for x in failures)}\n/menu")
    else:
        m.reply_text("Сообщение доставлено во все чаты.\n/menu")

dispatcher.add_handler(MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message), group=1)

# --- /edit, /delete, /getid ---
def edit_message(update: Update, context: CallbackContext):
    # ... ваш существующий код без изменений ...
    pass
def delete_message(update: Update, context: CallbackContext):
    # ... ваш существующий код без изменений ...
    pass
def get_chat_id(update: Update, context: CallbackContext):
    update.message.reply_text(f"ID: {update.message.chat.id}")

dispatcher.add_handler(CommandHandler("edit", edit_message, pass_args=True))
dispatcher.add_handler(CommandHandler("delete", delete_message))
dispatcher.add_handler(CommandHandler("getid", get_chat_id))

# --- Flask + Webhook ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

@app.route('/', methods=['GET'])
def index():
    return "Bot is running"

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
