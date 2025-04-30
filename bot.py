import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup, MessageEntity
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ENVIRONMENT ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- DATA ---
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
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]

# --- BOT & DISPATCHER ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- HELPERS ---
def rebuild_entities(text: str, entities: list[MessageEntity]) -> str:
    """
    Вставляем HTML-теги по списку MessageEntity.
    """
    if not entities:
        return text
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset+e.length, reverse=True):
        o, l = ent.offset, ent.length
        if ent.type == "bold":
            chars.insert(o, "<b>"); chars.insert(o+l+3, "</b>")
        elif ent.type == "italic":
            chars.insert(o, "<i>"); chars.insert(o+l+3, "</i>")
        elif ent.type == "underline":
            chars.insert(o, "<u>"); chars.insert(o+l+3, "</u>")
        elif ent.type == "code":
            chars.insert(o, "<code>"); chars.insert(o+l+6, "</code>")
        elif ent.type == "spoiler":
            chars.insert(o, "<u>"); chars.insert(o+l+3, "</u>")
        # CUSTOM_EMOJI и ссылки (<a>) при копировании через copy_message сохранятся
    return "".join(chars)

def forward_multimedia(msg: Update.message, chat_id: int):
    """
    Если это медиа, шлём соответствующим методом с HTML-подписью.
    Возвращает объект Message или None.
    """
    caption = rebuild_entities(msg.caption or "", msg.caption_entities or [])
    try:
        if msg.photo:
            return bot.send_photo(chat_id=chat_id,
                                  photo=msg.photo[-1].file_id,
                                  caption=caption,
                                  parse_mode="HTML",
                                  disable_web_page_preview=True)
        if msg.video:
            return bot.send_video(chat_id=chat_id,
                                  video=msg.video.file_id,
                                  caption=caption,
                                  parse_mode="HTML",
                                  disable_web_page_preview=True)
        if msg.audio:
            return bot.send_audio(chat_id=chat_id,
                                  audio=msg.audio.file_id,
                                  caption=caption,
                                  parse_mode="HTML")
        if msg.document:
            return bot.send_document(chat_id=chat_id,
                                     document=msg.document.file_id,
                                     caption=caption,
                                     parse_mode="HTML",
                                     disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"forward_multimedia fail: {e}")
    return None

# --- MENU COMMAND ---
def menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    # чистим все предыдущие состояния
    context.user_data.clear()
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)

dispatcher.add_handler(CommandHandler("menu", menu))

# --- HANDLE MENU SELECTION ---
def handle_main_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        return
    choice = update.message.text.strip()
    # Список чатов
    if choice == "Список чатов ФАБА":
        lines = ["Список чатов ФАБА:"]
        for c in ALL_CITIES:
            lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
        back = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
        return update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=back
        )

    # Отправка по всем чатам
    if choice == "Отправить сообщение во все чаты ФАБА":
        context.user_data["selected_chats"] = [c["chat_id"] for c in ALL_CITIES]
        return update.message.reply_text(
            "Теперь отправьте **ваше** сообщение (текст или медиа)\n"
            "или нажмите /menu для отмены.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    # Тестовая отправка
    if choice == "Тестовая отправка":
        context.user_data["pending_test"] = True
        return update.message.reply_text(
            "Введите текст или медиа для тестовой отправки.\n"
            "или нажмите /menu для отмены.",
            disable_web_page_preview=True
        )

    # Назад
    if choice == "Назад":
        return menu(update, context)

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & Filters.text & 
        Filters.regex("^(Список чатов ФАБА|Отправить сообщение во все чаты ФАБА|Тестовая отправка|Назад)$"),
        handle_main_menu
    ),
    group=0
)

# --- FORWARDING CONTENT ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    user_id = msg.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        return

    # Игнорируем меню-тексты и любые команды
    if msg.text and (msg.text.startswith("/") or msg.text in {
        "Список чатов ФАБА",
        "Отправить сообщение во все чаты ФАБА",
        "Тестовая отправка",
        "Назад"
    }):
        return

    # 1) Тестовая отправка
    if context.user_data.pop("pending_test", False):
        fails = []
        for cid in TEST_SEND_CHATS:
            if forward_multimedia(msg, cid) is None:
                # текст
                text = rebuild_entities(msg.text or "", msg.entities or [])
                try:
                    bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except:
                    fails.append(cid)
        reply = "Тестовое сообщение успешно отправлено." if not fails else f"Не удалось в: {fails}"
        update.message.reply_text(reply, disable_web_page_preview=True)
        return update.message.reply_text("Нажмите /menu для нового выбора.", disable_web_page_preview=True)

    # 2) Основная рассылка
    chosen = context.user_data.pop("selected_chats", None)
    if chosen:
        fails = []
        for cid in chosen:
            if forward_multimedia(msg, cid) is None:
                text = rebuild_entities(msg.text or "", msg.entities or [])
                try:
                    bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except:
                    fails.append(cid)
        reply = "Сообщение доставлено во все чаты." if not fails else f"Не доставлено в: {fails}"
        update.message.reply_text(reply, disable_web_page_preview=True)
        return update.message.reply_text("Нажмите /menu для нового выбора.", disable_web_page_preview=True)

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & (
            Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document
        ),
        forward_message
    ),
    group=1
)

# --- FLASK & WEBHOOK ---
app = Flask(__name__)

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
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
