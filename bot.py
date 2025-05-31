#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import sqlite3
import time
import threading
from math import floor, sqrt

from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup, ParseMode
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from telegram.utils.request import Request

# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Убедитесь, что эти переменные окружения заданы:
#   BOT_TOKEN="123456789:ABCDE..."
#   WEBHOOK_URL="https://<your-render-domain>.onrender.com"

# ID группы «Тюмень», в которой будем считать XP
TYUMEN_CHAT_ID = -1002241413860

# Файл SQLite для хранения XP
DB_PATH = "activity.db"

# XP-настройки
XP_PER_MESSAGE = 1          # +1 XP за любое сообщение
XP_PER_50_CHARS = 0.2       # +0.2 XP за каждые 50 символов текста
XP_MAX_BONUS = 4            # максимум бонуса за длину
XP_CAP_PER_MINUTE = 5       # максимум XP, начисляемый за одну минуту

# Список городов и их чат_id (осталось без изменений)
ALL_CITIES = [
    {"name": "Тюмень",        "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",   "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",       "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",    "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург", "link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
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
    {"name": "Тула",          "link": "https://t.me/+ZCq3GsGagIQ1NzRi", "chat_id": -1002678281080},
]

# Чаты для тестовой рассылки
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# Список админов, которым разрешено пользоваться меню и смотреть рейтинг
YOUR_ID = 296920330
ALLOWED_USER_IDS = {
    296920330,
    320303183,
    533773,
    327650534,
    533007308,
    136737738,
    1607945564
}

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ FLASK И DISPATCHER
# ==============================================================================

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4, use_context=True)

# ==============================================================================
# ФУНКЦИИ ДЛЯ SQLITE
# ==============================================================================

def init_db():
    """
    Создаёт файл activity.db и таблицу xp, если её ещё нет.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xp (
            user_id     INTEGER PRIMARY KEY,
            total_xp    REAL DEFAULT 0,
            last_msg_ts INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

# Инициализируем базу сразу при импорте (Gunicorn выполнит этот код при старте)
init_db()

# ==============================================================================
# ФУНКЦИИ ДЛЯ РАСЧЁТА И ЗАПИСИ XP
# ==============================================================================

def calc_message_xp(text: str) -> float:
    """
    Вычисляет XP за сообщение:
      - базово +1 XP,
      - +0.2 XP за каждые 50 символов текста (максимум XP_MAX_BONUS).
    """
    base = XP_PER_MESSAGE
    length_bonus = min((len(text) // 50) * XP_PER_50_CHARS, XP_MAX_BONUS)
    return base + length_bonus

def record_xp(update: Update, context: CallbackContext):
    """
    Обрабатывает текстовые/медиа-сообщения в группе «Тюмень»:
    начисляет XP и обновляет базу SQLite.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # Считаем XP только из группы «Тюмень»
    if chat.type not in ("group", "supergroup") or chat.id != TYUMEN_CHAT_ID:
        return
    if not user or user.is_bot:
        return

    text = message.text or message.caption or ""
    xp_gain = calc_message_xp(text)
    now_ts = int(time.time())
    minute_bound = now_ts - 60

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT total_xp, last_msg_ts FROM xp WHERE user_id = ?",
        (user.id,)
    )
    row = cur.fetchone()
    if row:
        total_xp, last_msg_ts = row
    else:
        total_xp, last_msg_ts = 0.0, 0

    # Если последнее сообщение было меньше минуты назад и
    # xp_gain превышает лимит за минуту, ничего не начисляем
    if last_msg_ts >= minute_bound and xp_gain > XP_CAP_PER_MINUTE:
        conn.close()
        return

    total_xp += xp_gain
    cur.execute(
        """
        INSERT INTO xp (user_id, total_xp, last_msg_ts)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            total_xp = excluded.total_xp,
            last_msg_ts = excluded.last_msg_ts
        """,
        (user.id, total_xp, now_ts)
    )
    conn.commit()
    conn.close()

# ==============================================================================
# КОМАНДЫ ДЛЯ РЕЙТИНГА (ТОЛЬКО В ЛИЧКУ И ТОЛЬКО ДЛЯ ALLOWED_USER_IDS)
# ==============================================================================

def cmd_rank(update: Update, context: CallbackContext):
    """
    /rank — показывает XP и уровень пользователя (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    # Работает только для личных сообщений и только в ALLOWED_USER_IDS
    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT total_xp FROM xp WHERE user_id = ?",
        (user.id,)
    )
    row = cur.fetchone()
    conn.close()

    total = row[0] if row else 0.0
    level = floor(sqrt(total))
    to_next = (level + 1) ** 2 - total

    text = (
        f"👤 Ваши очки (XP) в группе «Тюмень»: *{int(total)}*\n"
        f"🎓 Уровень: *{level}*  (до следующего уровня осталось *{int(to_next)}* XP)\n\n"
        "_XP начисляются только за сообщения в группе «Тюмень». "
        "Чтобы набрать XP, пишите туда как обычно._"
    )
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def cmd_top(update: Update, context: CallbackContext):
    """
    /top [N] — показывает топ-N пользователей по XP (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    # Тоже только для личных и только в ALLOWED_USER_IDS
    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    args = context.args
    try:
        n = int(args[0]) if args and args[0].isdigit() else 10
    except:
        n = 10
    n = max(1, min(n, 50))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, total_xp FROM xp ORDER BY total_xp DESC LIMIT ?",
        (n,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        update.message.reply_text(
            "Пока нет данных о рейтинге — никто ещё не писал в группу «Тюмень».",
            quote=True
        )
        return

    lines = [f"🏆 *Топ-{n} участников (по XP) в «Тюмень»:*"]
    rank = 1
    for user_id, xp in rows:
        try:
            user_obj = bot.get_chat(user_id)
            name = user_obj.username if user_obj.username else user_obj.full_name
        except:
            name = f"ID:{user_id}"
        lines.append(f"{rank}. {name} — *{int(xp)}* XP")
        rank += 1

    update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ==============================================================================
# ХЭНДЛЕРЫ МЕНЮ И РАССЫЛОК (ТОЛЬКО В ЛИЧКУ И ДЛЯ ALLOWED_USER_IDS)
# ==============================================================================

user_buffers = {}
user_waiting = {}
user_mode = {}

def main_menu_keyboard(uid):
    kb = [
        ["Рассылка по городам"],
        ["Список чатов ФАБА"]
    ]
    # Кнопка «Тестовая рассылка» видна только YOUR_ID
    if uid == YOUR_ID:
        kb.insert(0, ["Тестовая рассылка"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

def menu(update: Update, context: CallbackContext):
    """
    /menu — открывает главное меню (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    update.message.reply_text("Выберите действие:", reply_markup=main_menu_keyboard(user.id))

def start_test_broadcast(update: Update, context: CallbackContext):
    """
    Режим тестовой рассылки (личка, только YOUR_ID).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id != YOUR_ID:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "test"
    update.message.reply_text(
        "Отправляй любые сообщения (текст, фото, стикеры и т. д.). "
        "Когда закончишь — напиши /sendall."
    )

def start_city_broadcast(update: Update, context: CallbackContext):
    """
    Режим рассылки по городам (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "city"
    update.message.reply_text(
        "Отправляй любые сообщения для рассылки по всем городам. "
        "Когда закончишь — напиши /sendall."
    )

def send_chat_list(update: Update, context: CallbackContext):
    """
    Выводит список чатов ФАБА (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    lines = ["Список чатов ФАБА:"]
    for city in ALL_CITIES:
        lines.append(f"<a href='{city['link']}'>{city['name']}</a>")

    markup = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=markup
    )

def handle_back(update: Update, context: CallbackContext):
    """
    Кнопка «Назад» — возвращает в главное меню (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    update.message.reply_text("Выберите действие:", reply_markup=main_menu_keyboard(user.id))

def add_to_buffer(update: Update, context: CallbackContext):
    """
    Добавляет сообщение в буфер для рассылки (личка, только админы, если открыт буфер).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS or not user_waiting.get(user.id):
        return
    if update.message.text and update.message.text.startswith("/"):
        return

    user_buffers.setdefault(user.id, []).append(update.message)
    if len(user_buffers[user.id]) == 1:
        update.message.reply_text(
            "Сообщение добавлено к рассылке. Когда закончите — напишите или нажмите на ➡️ /sendall, и рассылка уйдет."
        )

def sendall(update: Update, context: CallbackContext):
    """
    /sendall — отправляет накопленные сообщения из буфера в выбранные чаты.
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    if not user_buffers.get(user.id):
        update.message.reply_text("Нет сообщений для рассылки.")
        return

    if user_mode.get(user.id) == "city":
        chat_ids = [c["chat_id"] for c in ALL_CITIES]
    else:
        chat_ids = TEST_SEND_CHATS

    for msg in user_buffers[user.id]:
        for chat_id in chat_ids:
            try:
                bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка при пересылке: {e}")

    update.message.reply_text("Рассылка завершена.\nЧтобы начать заново, нажмите /menu")
    user_buffers[user.id] = []
    user_waiting[user.id] = False
    user_mode[user.id] = None

# ==============================================================================
# РЕГИСТРАЦИЯ ХЭНДЛЕРОВ
# ==============================================================================

# 1) Хэндлер записи XP из группы «Тюмень»
dispatcher.add_handler(
    MessageHandler(
        Filters.chat(TYUMEN_CHAT_ID)
        & ~Filters.command
        & (Filters.text | Filters.photo | Filters.video | Filters.document),
        record_xp
    ),
    group=1
)

# 2) Команды /rank и /top (личка, только ALLOWED_USER_IDS)
dispatcher.add_handler(CommandHandler("rank", cmd_rank), group=2)
dispatcher.add_handler(CommandHandler("top", cmd_top), group=2)

# 3) Хэндлеры меню и рассылок (личка, только ALLOWED_USER_IDS)
dispatcher.add_handler(CommandHandler("menu", menu), group=2)
dispatcher.add_handler(MessageHandler(Filters.regex("^Тестовая рассылка$"), start_test_broadcast), group=2)
dispatcher.add_handler(MessageHandler(Filters.regex("^Рассылка по городам$"), start_city_broadcast), group=2)
dispatcher.add_handler(MessageHandler(Filters.regex("^Список чатов ФАБА$"), send_chat_list), group=2)
dispatcher.add_handler(MessageHandler(Filters.regex("^Назад$"), handle_back), group=2)
dispatcher.add_handler(CommandHandler("sendall", sendall), group=2)
dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private & ~Filters.command,
        add_to_buffer
    ),
    group=2
)

# ==============================================================================
# WEBHOOK-РУЧКА: отвечаем мгновенно, а process_update выполняем в фоне
# ==============================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)

    # Запускаем диспетчер в отдельном потоке, чтобы вернуть HTTP 200 сразу
    threading.Thread(
        target=dispatcher.process_update,
        args=(update,)
    ).start()

    return "OK", 200

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

# ==============================================================================
# УСТАНОВКА WEBHOOK (для Gunicorn/Render — выполняется при импорте модуля)
# ==============================================================================

# Удаляем старый webhook и ставим новый сразу при старте процесса
try:
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"Webhook установлен: {WEBHOOK_URL}/webhook")
except Exception as e:
    logger.error(f"Не удалось установить webhook: {e}")

# ==============================================================================
# ЗАПУСК ПРИ ЛОКАЛЬНОЙ ОТЛАДКЕ
# ==============================================================================
if __name__ == "__main__":
    # Если запускаешь локально (а не через Gunicorn), пропиши переменные окружения
    # и вызови Flask.run для отладки:
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
