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

# Список всех городских чатов, где бот считает XP
ALL_CITIES = [
    {"name": "Тюмень",         "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",    "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",        "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",     "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург","link": "https://t.me/+EWj9jKhAvV82NWIy","chat_id": -1002152780476},
    {"name": "Москва",         "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург",   "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",        "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",       "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",           "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002506541314},
    {"name": "Чита",           "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград",      "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар",      "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь",          "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара",         "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",    "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",         "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",      "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",      "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
    {"name": "Тула",           "link": "https://t.me/+ZCq3GsGagIQ1NzRi", "chat_id": -1002678281080},
]

# Для тестовой (небоевой) рассылки
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# Админские ID
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

# XP-настройки
XP_PER_MESSAGE = 1          # +1 XP за любое сообщение
XP_PER_50_CHARS = 0.2       # +0.2 XP за каждые 50 символов текста
XP_MAX_BONUS = 4            # максимум бонуса за длину
XP_CAP_PER_MINUTE = 5       # максимум XP, начисляемый за одну минуту

# Путь к файлу SQLite
DB_PATH = "activity.db"

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
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ==============================================================================

def init_db():
    """
    Создаёт файл activity.db и таблицу xp, если их ещё нет.
    Таблица xp хранит chat_id, user_id, total_xp и last_msg_ts.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xp (
            chat_id     INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            total_xp    REAL DEFAULT 0,
            last_msg_ts INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )
        """
    )
    conn.commit()
    conn.close()

# Вызываем сразу, чтобы при импорте таблица была создана
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
    Обрабатывает сообщения (text / media) в любых чатах из ALL_CITIES:
    начисляет XP и обновляет базу SQLite.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # Обрабатываем только чаты из ALL_CITIES
    valid_chat_ids = {city["chat_id"] for city in ALL_CITIES}
    if chat.type not in ("group", "supergroup") or chat.id not in valid_chat_ids:
        return
    if not user or user.is_bot:
        return

    text = message.text or message.caption or ""
    xp_gain = calc_message_xp(text)
    now_ts = int(time.time())
    minute_bound = now_ts - 60

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Получаем текущее значение XP и время последнего сообщения для этого (chat_id, user_id)
    cur.execute(
        "SELECT total_xp, last_msg_ts FROM xp WHERE chat_id = ? AND user_id = ?",
        (chat.id, user.id)
    )
    row = cur.fetchone()
    if row:
        total_xp, last_msg_ts = row
    else:
        total_xp, last_msg_ts = 0.0, 0

    # Лимит XP за минуту в рамках одной группы:
    if last_msg_ts >= minute_bound and xp_gain > XP_CAP_PER_MINUTE:
        conn.close()
        return

    total_xp += xp_gain
    cur.execute(
        """
        INSERT INTO xp (chat_id, user_id, total_xp, last_msg_ts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            total_xp = excluded.total_xp,
            last_msg_ts = excluded.last_msg_ts
        """,
        (chat.id, user.id, total_xp, now_ts)
    )
    conn.commit()
    conn.close()

# ==============================================================================
# КОМАНДЫ /rank и /top (личка, только админы)
# ==============================================================================

def cmd_rank(update: Update, context: CallbackContext):
    """
    /rank [<city_name>]
    Если <city_name> указан (название из ALL_CITIES), показывает XP и уровень пользователя
    в этой группе. Если не указан — показывает суммарный (глобальный) XP по всем чатам.
    Работает только в личке и только для ALLOWED_USER_IDS.
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    args = context.args
    # Собираем map from city name (in lowercase) to chat_id
    city_map = {city["name"].lower(): city["chat_id"] for city in ALL_CITIES}

    if args:
        city_name = " ".join(args).lower()
        if city_name not in city_map:
            update.message.reply_text(
                f"Город «{' '.join(args)}» не найден. Список доступных городов: {', '.join(city_map.keys())}.",
                quote=True
            )
            return
        target_chat_id = city_map[city_name]

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT total_xp FROM xp WHERE chat_id = ? AND user_id = ?",
            (target_chat_id, user.id)
        )
        row = cur.fetchone()
        conn.close()

        total = row[0] if row else 0.0
        level = floor(sqrt(total))
        to_next = (level + 1) ** 2 - total

        text = (
            f"👤 Ваши очки (XP) в группе «{city_name.title()}»: *{int(total)}*\n"
            f"🎓 Уровень: *{level}*  (до следующего уровня осталось *{int(to_next)}* XP)\n\n"
            f"_XP начисляются только за сообщения в группе «{city_name.title()}». "
            "Чтобы набрать XP, пишите туда как обычно._"
        )
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        # Глобальная статистика: суммируем XP по всем чатам
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT SUM(total_xp) FROM xp WHERE user_id = ?",
            (user.id,)
        )
        row = cur.fetchone()
        conn.close()

        total = row[0] if row and row[0] is not None else 0.0
        level = floor(sqrt(total))
        to_next = (level + 1) ** 2 - total

        text = (
            f"👤 Ваши суммарные очки (XP) по всем городам: *{int(total)}*\n"
            f"🎓 Уровень: *{level}*  (до следующего уровня осталось *{int(to_next)}* XP)\n\n"
            "_XP начисляются за сообщения во всех группах. Чтобы посмотреть рейтинг в конкретном городе, "
            "напишите /rank <название_города>._"
        )
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def cmd_top(update: Update, context: CallbackContext):
    """
    /top [<city_name>] [N]
    Если <city_name> указан, показывает топ-N пользователей по XP в этой группе.
    Если не указан, показывает топ-N пользователей по суммарному XP во всех чатах.
    По умолчанию N=10.
    Работает только в личке и только для ALLOWED_USER_IDS.
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    args = context.args
    city_map = {city["name"].lower(): city["chat_id"] for city in ALL_CITIES}
    target_chat_id = None
    n = 10

    # Определяем, передали ли сначала название города, затем число
    if args:
        # Если последний аргумент цифра, считаем это N
        if args[-1].isdigit():
            n = max(1, min(int(args[-1]), 50))
            city_part = " ".join(args[:-1]).strip().lower()
        else:
            city_part = " ".join(args).strip().lower()

        if city_part:
            if city_part not in city_map:
                update.message.reply_text(
                    f"Город «{city_part}» не найден. Список доступных: {', '.join(city_map.keys())}.",
                    quote=True
                )
                return
            target_chat_id = city_map[city_part]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if target_chat_id:
        # Топ в конкретном чате
        cur.execute(
            "SELECT user_id, total_xp FROM xp WHERE chat_id = ? ORDER BY total_xp DESC LIMIT ?",
            (target_chat_id, n)
        )
        rows = cur.fetchall()
        title = f"Топ-{n} в «{args[0].title()}»"
    else:
        # Глобальный топ: суммируем по user_id
        cur.execute(
            """
            SELECT user_id, SUM(total_xp) AS sum_xp
            FROM xp
            GROUP BY user_id
            ORDER BY sum_xp DESC
            LIMIT ?
            """,
            (n,)
        )
        rows = cur.fetchall()
        title = f"Глобальный топ-{n} (по всем городам)"

    conn.close()

    if not rows:
        update.message.reply_text("Пока нет данных для этого запроса.", quote=True)
        return

    lines = [f"🏆 *{title}:*"]
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
# ХЭНДЛЕРЫ МЕНЮ И РАССЫЛОК (личка, только ALLOWED_USER_IDS)
# ==============================================================================

user_buffers = {}
user_waiting = {}
user_mode = {}

def main_menu_keyboard(uid):
    kb = [
        ["Рассылка по городам"],
        ["Список чатов ФАБА"]
    ]
    if uid == YOUR_ID:
        kb.insert(0, ["Тестовая рассылка"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

def menu(update: Update, context: CallbackContext):
    """
    /menu — открывает главное меню, только для админов (личка).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    update.message.reply_text("Выберите действие:", reply_markup=main_menu_keyboard(user.id))

def start_test_broadcast(update: Update, context: CallbackContext):
    """
    Тестовая рассылка (личка, только YOUR_ID).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id != YOUR_ID:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "test"
    update.message.reply_text(
        "Отправляй любые сообщения (текст, фото, стикеры и т. д.). Когда закончишь — напиши /sendall."
    )

def start_city_broadcast(update: Update, context: CallbackContext):
    """
    Рассылка по всем городам (личка, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "city"
    update.message.reply_text(
        "Отправляй любые сообщения для рассылки по всем городам. Когда закончишь — напиши /sendall."
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
    Кнопка «Назад» возвращает в главное меню (личка, только админы).
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

# 1) XP-запись (все чаты из ALL_CITIES)
valid_chat_ids = {city["chat_id"] for city in ALL_CITIES}
dispatcher.add_handler(
    MessageHandler(
        Filters.chat(valid_chat_ids)
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

    # Запускаем обработку в отдельном потоке, чтобы вернуть HTTP 200 сразу
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
