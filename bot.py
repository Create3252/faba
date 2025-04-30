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
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 533007308, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Для удобства lookup: chat_id -> название
city_lookup = {city["chat_id"]: city["name"] for city in ALL_CITIES}

# --- СОЗДАЁМ БОТА И ДИСПЕТЧЕР ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- ФУНКЦИЯ РАЗБОРА caption_entities ---
def rebuild_caption_with_entities(msg: Update) -> str:
    text = msg.caption or ""
    entities = msg.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start, end = ent.offset, ent.offset + ent.length
        tag = None
        if ent.type == "bold": tag = ('<b>','</b>')
        elif ent.type == "italic": tag = ('<i>','</i>')
        elif ent.type == "underline": tag = ('<u>','</u>')
        elif ent.type == "strikethrough": tag = ('<s>','</s>')
        elif ent.type == "code": tag = ('<code>','</code>')
        elif ent.type == "spoiler": tag = ('<spoiler>','</spoiler>')
        if tag:
            chars.insert(end, tag[1])
            chars.insert(start, tag[0])
    return "".join(chars)

# --- УНИВЕРСАЛЬНЫЙ FORWARD С ENTITY И МЕДИА ---
def _forward_with_entities(msg, chat_id):
    # медиа
    if msg.photo:
        return bot.send_photo(chat_id=chat_id,
                              photo=msg.photo[-1].file_id,
                              caption=rebuild_caption_with_entities(msg),
                              caption_entities=msg.caption_entities)
    if msg.video:
        return bot.send_video(chat_id=chat_id,
                              video=msg.video.file_id,
                              caption=rebuild_caption_with_entities(msg),
                              caption_entities=msg.caption_entities)
    if msg.audio:
        return bot.send_audio(chat_id=chat_id,
                              audio=msg.audio.file_id,
                              caption=rebuild_caption_with_entities(msg),
                              caption_entities=msg.caption_entities)
    if msg.document:
        return bot.send_document(chat_id=chat_id,
                                 document=msg.document.file_id,
                                 caption=rebuild_caption_with_entities(msg),
                                 caption_entities=msg.caption_entities)
    # текст
    return bot.send_message(chat_id=chat_id,
                             text=msg.text or "",
                             entities=msg.entities)

# --- МЕНЮ ---
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав.")
        return
    kb = [["Список чатов ФАБА","Отправить сообщение во все чаты ФАБА"],["Тестовая отправка"]]
    update.message.reply_text("Выберите:",reply_markup=ReplyKeyboardMarkup(kb,resize_keyboard=True,one_time_keyboard=True))
    context.user_data['pending_main_menu']=True

dispatcher.add_handler(CommandHandler('menu', menu))

# --- ОБРАБОТКА МЕНЮ (group=0) ---
def handle_main_menu(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if not context.user_data.pop('pending_main_menu',False):
        return False
    if text=='Список чатов ФАБА':
        lines=[f"<a href='{c['link']}'>{c['name']}</a>" if c['link'] else c['name'] for c in ALL_CITIES]
        update.message.reply_text("Список чатов ФАБА:\n"+"\n".join(lines),
                                  parse_mode="HTML",disable_web_page_preview=True,
                                  reply_markup=ReplyKeyboardMarkup([["Назад"]],resize_keyboard=True,one_time_keyboard=True))
        raise DispatcherHandlerStop
    if text=='Отправить сообщение во все чаты ФАБА':
        context.user_data['selected_chats']=[c['chat_id'] for c in ALL_CITIES]
        update.message.reply_text("Выбрано рассылку во все чаты. Пришлите сообщение.\n/​menu для меню.")
        raise DispatcherHandlerStop
    if text=='Тестовая отправка':
        context.user_data['pending_test']=True
        update.message.reply_text("Введите текст или медиа для тестовой отправки.")
        raise DispatcherHandlerStop
    if text=='Назад':
        return menu(update,context)

dispatcher.add_handler(MessageHandler(Filters.private & ~Filters.command, handle_main_menu),group=0)

# --- ПЕРЕСЫЛКА (group=1) ---
def forward_message(update: Update, context: CallbackContext):
    msg=update.message
    if msg.chat.type!='private': return
    # тестовая
    if context.user_data.pop('pending_test',False):
        fails=[]
        for cid in TEST_SEND_CHATS:
            try: _forward_with_entities(msg,cid)
            except: fails.append(cid)
        update.message.reply_text(
            f"Не удалось: {fails}\n/​menu" if fails else "Тест отправлен.\n/​menu"
        )
        return
    # обычная
    chat_ids=context.user_data.pop('selected_chats',[])
    if not chat_ids:
        msg.reply_text("Сначала /menu")
        return
    fails=[]
    for cid in chat_ids:
        try: _forward_with_entities(msg,cid)
        except: fails.append(cid)
    msg.reply_text(
        f"Не получилось: {fails}\n/​menu" if fails else "Отправлено во все чаты.\n/​menu"
    )

dispatcher.add_handler(MessageHandler(Filters.private & ~Filters.command, forward_message),group=1)

# /edit /delete /getid опущены (остались без изменений)

# --- FLASK ---
app=Flask(__name__)
@app.route('/webhook',methods=['POST'])
