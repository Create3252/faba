import os
import time
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

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- ДАННЫЕ О ГОРОДАХ И ТЕСТОВЫХ ЧАТАХ ---
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
]
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# --- ПРАВА ДОСТУПА ---
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- УТИЛИТЫ ДЛЯ HTML-ФОРМАТИРОВАНИЯ ---
def rebuild_entities(text: str, entities) -> str:
    """
    Вставляет в текст HTML-теги на основе entities.
    Обрабатывает bold, italic, underline, strikethrough, code, url и custom_emoji.
    """
    if not text or not entities:
        return text or ""
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        if ent.type == "bold":
            chars.insert(end, "</b>"); chars.insert(start, "<b>")
        elif ent.type == "italic":
            chars.insert(end, "</i>"); chars.insert(start, "<i>")
        elif ent.type == "underline":
            chars.insert(end, "</u>"); chars.insert(start, "<u>")
        elif ent.type == "strikethrough":
            chars.insert(end, "</s>"); chars.insert(start, "<s>")
        elif ent.type == "code":
            chars.insert(end, "</code>"); chars.insert(start, "<code>")
        elif ent.type == "url":
            url = ent.url or text[start:end]
            chars.insert(end, "</a>")
            chars.insert(start, f"<a href=\"{url}\">")
        elif ent.type == "custom_emoji":
            # при copy_message custom emoji сохраняются,
            # при send_message они тоже сохранятся как символы текста
            pass
    return "".join(chars)

# --- МЕНЮ ---
def menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА ВЫБОРА В МЕНЮ ---
def handle_main_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        return
    if not context.user_data.get("pending_main_menu"):
        return
    choice = update.message.text.strip()
    context.user_data.pop("pending_main_menu", None)

    if choice == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for city in ALL_CITIES:
            lines.append(f"<a href=\"{city['link']}\">{city['name']}</a>")
        back = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        return update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=back
        )

    if choice == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        return update.message.reply_text(
            "Теперь отправьте сообщение (текст или медиа) и оно будет разослано во все чаты.\n"
            "Нажмите /menu для отмены.",
            disable_web_page_preview=True
        )

    if choice == "Тестовая отправка":
        context.user_data["pending_test"] = True
        return update.message.reply_text(
            "Введите текст или медиа для тестовой отправки.\n"
            "Нажмите /menu для отмены.",
            disable_web_page_preview=True
        )

    if choice == "Назад":
        return menu(update, context)

    update.message.reply_text("Неверный выбор, используйте /menu")

    # останавливаем дальнейшую передачу этому сообщению
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- ФУНКЦИЯ ПЕРЕСЫЛКИ МЕДИА (с сохранением caption и без предпросмотра ссылок) ---
def forward_multimedia(msg, chat_id):
    caption = rebuild_entities(msg.caption or "", msg.caption_entities or [])
    if msg.photo:
        return bot.send_photo(
            chat_id=chat_id,
            photo=msg.photo[-1].file_id,
            caption=caption,
            parse_mode="HTML",
            disable_notification=True
        )
    if msg.video:
        return bot.send_video(
            chat_id=chat_id,
            video=msg.video.file_id,
            caption=caption,
            parse_mode="HTML",
            disable_notification=True
        )
    if msg.audio:
        return bot.send_audio(
            chat_id=chat_id,
            audio=msg.audio.file_id,
            caption=caption,
            parse_mode="HTML",
            disable_notification=True
        )
    if msg.document:
        return bot.send_document(
            chat_id=chat_id,
            document=msg.document.file_id,
            caption=caption,
            parse_mode="HTML",
            disable_notification=True
        )
    return None  # не медиа

# --- ГЛАВНЫЙ ХЕНДЛЕР ПЕРЕСЫЛКИ ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    uid = msg.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return

    # 1) тестовая отправка?
    if context.user_data.pop("pending_test", False):
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                if forward_multimedia(msg, cid) is None:
                    # текстовое сообщение
                    text = rebuild_entities(msg.text or "", msg.entities or [])
                    bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                logging.info(f"[test] sent to {cid}")
            except Exception as e:
                logging.error(f"[test] fail to {cid}: {e}")
                failures.append(cid)
        if failures:
            update.message.reply_text(
                f"Не удалось отправить в тестовые чаты: {', '.join(map(str, failures))}.",
                disable_web_page_preview=True
            )
        else:
            update.message.reply_text(
                "Тестовое сообщение успешно отправлено во все тестовые чаты.",
                disable_web_page_preview=True
            )
        update.message.reply_text("Нажмите /menu для нового выбора.", disable_web_page_preview=True)
        return

    # 2) основная рассылка?
    chat_ids = context.user_data.pop("selected_chats", None)
    if chat_ids:
        failures = []
        for cid in chat_ids:
            try:
                if forward_multimedia(msg, cid) is None:
                    text = rebuild_entities(msg.text or "", msg.entities or [])
                    bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                logging.info(f"[all] sent to {cid}")
            except Exception as e:
                logging.error(f"[all] fail to {cid}: {e}")
                failures.append(cid)
        if failures:
            update.message.reply_text(
                f"Не удалось отправить в: {', '.join(map(str, failures))}.",
                disable_web_page_preview=True
            )
        else:
            update.message.reply_text(
                "Сообщение успешно доставлено во все чаты.",
                disable_web_page_preview=True
            )
        update.message.reply_text("Нажмите /menu для нового выбора.", disable_web_page_preview=True)
        return

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document
        ),
        forward_message
    ),
    group=1
)

# --- FLASK / WEBHOOK ---
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

if __name__ == '__main__':
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
