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

# --- ПОЛУЧАЕМ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# --- ДАННЫЕ О ГОРОДАХ и ТЕСТОВЫХ ЧАТАХ ---
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

# Список ID пользователей, которым разрешено использовать бота
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Для удобства lookup: chat_id → название
city_lookup = {c['chat_id']: c['name'] for c in ALL_CITIES}

# --- ИНИЦИАЛИЗАЦИЯ ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def rebuild_caption_with_entities(update: Update) -> str:
    # Собираем HTML-метки по caption_entities
    if not update.message.caption:
        return ""
    text, entities = update.message.caption, update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset+e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        tag = {
            'bold': ('<b>', '</b>'),
            'italic': ('<i>', '</i>'),
            'underline': ('<u>', '</u>'),
            'strikethrough': ('<s>', '</s>'),
            'code': ('<code>', '</code>'),
            'spoiler': ('<u>', '</u>'),
        }.get(ent.type)
        if tag:
            chars.insert(end, tag[1])
            chars.insert(start, tag[0])
    return ''.join(chars)


def send_message_with_retry(chat_id, text, max_attempts=3, delay=5):
    for attempt in range(1, max_attempts+1):
        try:
            return bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке в {chat_id}: {e}")
            if 'Chat not found' in str(e):
                return None
            time.sleep(delay)
    return None

# --- МЕНЮ ---
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав для использования этого бота.")
    kb = [["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"], ["Тестовая отправка"]]
    markup = ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data['pending_main_menu'] = True


dispatcher.add_handler(CommandHandler('menu', menu))

# --- ОБРАБОТКА ВЫБОРА ---
def handle_main_menu(update: Update, context: CallbackContext) -> bool:
    user = update.message.from_user.id
    if user not in ALLOWED_USER_IDS or 'pending_main_menu' not in context.user_data:
        return False
    text = update.message.text.strip()
    context.user_data.pop('pending_main_menu', None)

    if text == 'Список чатов ФАБА':
        lines = ['Список чатов ФАБА:']
        for c in ALL_CITIES:
            if c.get('link'):
                lines.append(f"<a href='{c['link']}'>{c['name']}</a>")
            else:
                lines.append(c['name'])
        markup = ReplyKeyboardMarkup([['Назад']], one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text('\n'.join(lines), parse_mode='HTML', disable_web_page_preview=True, reply_markup=markup)
        return True

    if text == 'Отправить сообщение во все чаты ФАБА':
        context.user_data['selected_chats'] = [c['chat_id'] for c in ALL_CITIES]
        update.message.reply_text("Теперь отправьте сообщение.\nНажмите /menu для отмены.")
        return True

    if text == 'Тестовая отправка':
        context.user_data['pending_test'] = True
        update.message.reply_text("Введите текст или медиа для тестовой отправки.\nНажмите /menu для отмены.")
        return True

    if text == 'Назад':
        menu(update, context)
        return True

    return False


dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu),
    group=0
)

# --- ПЕРЕСЫЛКА ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    if not msg or msg.chat.type != 'private':
        return

    # Тестовая рассылка
    if context.user_data.pop('pending_test', False):
        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Не удалось тестово копировать в {cid}: {e}")
                failures.append(cid)
        text = (f"Часть тестовых сообщений не отправлены в: {', '.join(map(str, failures))}" if failures 
                else "Тестовое сообщение успешно отправлено во все тестовые чаты.")
        update.message.reply_text(text + "\n/menu для нового выбора.")
        return

    # Основная рассылка
    chat_ids = context.user_data.pop('selected_chats', None)
    if not chat_ids:
        return msg.reply_text("Сначала выберите действие через /menu.")

    failures = []
    for cid in chat_ids:
        try:
            # если текстовый with ссылками
            if msg.text and msg.entities and any(ent.type in ('url','text_link') for ent in msg.entities):
                bot.send_message(chat_id=cid, text=msg.text, parse_mode='HTML', disable_web_page_preview=True)
            else:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        except Exception as e:
            logging.error(f"Не удалось копировать в {cid}: {e}")
            failures.append(cid)

    text = (f"Часть сообщений не отправлена в: {', '.join(map(str, failures))}" if failures 
            else "Сообщение успешно доставлено во все чаты.")
    msg.reply_text(text + "\n/menu для нового выбора.")


dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message),
    group=1
)

# --- /edit, /delete, /getid ---
def edit_message(update: Update, context: CallbackContext):
    ...  # аналогично вашему коду

def delete_message(update: Update, context: CallbackContext):
    ...  # аналогично вашему коду

def get_chat_id(update: Update, context: CallbackContext):
    update.message.reply_text(f"ID этой группы: {update.message.chat.id}")

dispatcher.add_handler(CommandHandler("edit", edit_message, pass_args=True))
dispatcher.add_handler(CommandHandler("delete", delete_message))
dispatcher.add_handler(CommandHandler("getid", get_chat_id))

# --- ФЛАСК + ВЕБХУК ---
app = Flask(__name__)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return 'OK'

@app.route('/ping', methods=['GET'])
def ping(): return 'pong'
@app.route('/', methods=['GET'])
def index(): return 'Bot is running'

if __name__ == '__main__':
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)))
