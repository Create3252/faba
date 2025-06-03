#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import sqlite3
import time
import threading
from math import floor, sqrt

from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup, ParseMode, InputFile
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

BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Список всех городских чатов (для начисления XP)
ALL_CITIES = [
    {"name": "Тюмень",          "link": "https://t.me/+3AjZ_Eo2H-NjYWJi", "chat_id": -1002241413860},
    {"name": "Новосибирск",     "link": "https://t.me/+wx20YVCwxmo3YmQy", "chat_id": -1002489311984},
    {"name": "Сахалин",         "link": "https://t.me/+FzQ_jEYX8AtkMzNi", "chat_id": -1002265902434},
    {"name": "Красноярск",      "link": "https://t.me/+lMTDVPF0syRiYzdi", "chat_id": -1002311750873},
    {"name": "Санкт-Петербург", "link": "https://t.me/+EWj9jKhAvV82NWIy", "chat_id": -1002152780476},
    {"name": "Москва",          "link": "https://t.me/+qokFNNnfhQdiYjQy", "chat_id": -1002182445604},
    {"name": "Екатеринбург",    "link": "https://t.me/+J2ESyZJyOAk2YzYy", "chat_id": -1002392430562},
    {"name": "Иркутск",         "link": "https://t.me/+TAoCnfoePUJmNzhi", "chat_id": -1002255012184},
    {"name": "Оренбург",        "link": "https://t.me/+-Y_1N0HnePUxZjZi", "chat_id": -1002316600732},
    {"name": "Крым",            "link": "https://t.me/+uC5IEnQWsmFhM2Ni", "chat_id": -1002506541314},
    {"name": "Чита",            "link": "https://t.me/+yMeI0CjltLphZWYy", "chat_id": -1002563254789},
    {"name": "Волгоград",       "link": "https://t.me/+ODxw0mfq73M4NGFi", "chat_id": -1002562049204},
    {"name": "Краснодар",       "link": "https://t.me/+a9_1fWyGvAc1NzZi", "chat_id": -1002297851122},
    {"name": "Пермь",           "link": "https://t.me/+lgM27u0cnp8wNjAy", "chat_id": -1002298810010},
    {"name": "Самара",          "link": "https://t.me/+SLCllcYKCUFlNjk6", "chat_id": -1002589409715},
    {"name": "Владивосток",     "link": "https://t.me/+Dpb3ozk_4Dc5OTYy", "chat_id": -1002438533236},
    {"name": "Донецк",          "link": "https://t.me/+nGkS5gfvvQxjNmRi", "chat_id": -1002328107804},
    {"name": "Хабаровск",       "link": "https://t.me/+SrnvRbMo3bA5NzVi", "chat_id": -1002480768813},
    {"name": "Челябинск",       "link": "https://t.me/+ZKXj5rmcmMw0MzQy", "chat_id": -1002374636424},
    {"name": "Тула",            "link": "https://t.me/+ZCq3GsGagIQ1NzRi", "chat_id": -1002678281080},
]

# Чаты для тестовой рассылки (не боевые)
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]

# ID админов (которые могут вызывать меню, /top, /rank, /dbdump, /dbpath, /senddb и т.д.)
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

# Настройки начисления XP
XP_PER_MESSAGE    = 1      # +1 XP за любое сообщение
XP_PER_50_CHARS   = 0.2    # +0.2 XP за каждые 50 символов текста (максимум до XP_MAX_BONUS)
XP_MAX_BONUS      = 4      # максимум бонуса за длину
XP_CAP_PER_MINUTE = 5      # максимум XP, начисляемый за одну минуту

# Путь к файлу SQLite (лежит рядом с bot.py)
DB_PATH = "activity.db"

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ Flask И Dispatcher
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
    Создаёт таблицу xp (если её ещё нет) с полями:
      chat_id, user_id, total_xp, last_msg_ts, first_name, last_name.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xp (
            chat_id     INTEGER     NOT NULL,
            user_id     INTEGER     NOT NULL,
            total_xp    REAL        DEFAULT 0,
            last_msg_ts INTEGER     DEFAULT 0,
            first_name  TEXT        DEFAULT '',
            last_name   TEXT        DEFAULT '',
            PRIMARY KEY(chat_id, user_id)
        )
        """
    )
    conn.commit()
    conn.close()

# При старте сразу создаём таблицу, если её нет
init_db()

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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

def get_city_name(chat_id: int) -> str:
    """
    По chat_id возвращает название города из ALL_CITIES,
    или "Неизвестно", если chat_id не найден.
    """
    for city in ALL_CITIES:
        if city["chat_id"] == chat_id:
            return city["name"]
    return "Неизвестно"

# ==============================================================================
# ХЭНДЛЕР ЗАПИСИ XP В БАЗУ
# ==============================================================================

def record_xp(update: Update, context: CallbackContext):
    """
    Ловит все сообщения (текст, фото, видео, документы) в чатах из ALL_CITIES:
    - считает XP (1 базово + бонус за длину),
    - применяет лимит XP_CAP_PER_MINUTE,
    - сохраняет (или обновляет) запись в таблице xp вместе с first_name и last_name.
    """
    message = update.effective_message
    chat    = update.effective_chat
    user    = update.effective_user

    # Если сообщение пришло не из городского чата или пришло от другого бота, пропускаем
    valid_chat_ids = {city["chat_id"] for city in ALL_CITIES}
    if chat.type not in ("group", "supergroup") or chat.id not in valid_chat_ids:
        return
    if not user or user.is_bot:
        return

    text = message.text or message.caption or ""
    xp_gain = calc_message_xp(text)
    now_ts = int(time.time())
    minute_bound = now_ts - 60

    first_name = user.first_name or ""
    last_name  = user.last_name  or ""

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Получаем текущее total_xp и время последнего сообщения для этого (chat_id, user_id)
    cur.execute(
        "SELECT total_xp, last_msg_ts FROM xp WHERE chat_id = ? AND user_id = ?",
        (chat.id, user.id)
    )
    row = cur.fetchone()
    if row:
        total_xp, last_msg_ts = row
    else:
        total_xp, last_msg_ts = 0.0, 0

    # Анти-флуд: не начисляем более XP_CAP_PER_MINUTE за минуту
    if last_msg_ts >= minute_bound and xp_gain > XP_CAP_PER_MINUTE:
        conn.close()
        return

    total_xp += xp_gain

    # Вставляем или обновляем запись вместе с именами
    cur.execute(
        """
        INSERT INTO xp (chat_id, user_id, total_xp, last_msg_ts, first_name, last_name)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            total_xp    = excluded.total_xp,
            last_msg_ts = excluded.last_msg_ts,
            first_name  = excluded.first_name,
            last_name   = excluded.last_name
        """,
        (chat.id, user.id, total_xp, now_ts, first_name, last_name)
    )
    conn.commit()
    conn.close()

# ==============================================================================
# КОМАНДА /top — ТОП-РЕЙТИНГ (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

def cmd_top(update: Update, context: CallbackContext):
    """
    /top [<город>] [N]
    - Если указан <город>, выводит топ-N пользователей по XP в этом чате.
    - Иначе выводит топ-N пользователей глобально (сумма XP по всем чатам).
    N по умолчанию = 10. В ответе кликабельное имя и чат в скобках.
    Работает только в личном диалоге и только для админов (ALLOWED_USER_IDS).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    args = context.args
    city_map = {city["name"].lower(): city["chat_id"] for city in ALL_CITIES}
    target_chat_id = None
    n = 10

    # Если последний аргумент — цифра, это N; иначе весь текст = название города
    if args:
        if args[-1].isdigit():
            n = max(1, min(int(args[-1]), 50))
            city_part = " ".join(args[:-1]).strip().lower()
        else:
            city_part = " ".join(args).strip().lower()

        if city_part:
            if city_part not in city_map:
                update.message.reply_text(
                    f"Город «{city_part}» не найден. Доступные: {', '.join(city_map.keys())}.",
                    quote=True
                )
                return
            target_chat_id = city_map[city_part]

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    lines = []

    if target_chat_id:
        # Топ-N в конкретном чате
        cur.execute(
            "SELECT user_id, total_xp, first_name, last_name "
            "FROM xp WHERE chat_id = ? ORDER BY total_xp DESC LIMIT ?",
            (target_chat_id, n)
        )
        rows = cur.fetchall()
        city_name_display = get_city_name(target_chat_id)
        title = f"Топ-{n} в «{city_name_display}»"
        if not rows:
            update.message.reply_text("Пока нет данных.", quote=True)
            conn.close()
            return

        lines.append(f"🏆 {title}:")
        rank = 1
        for user_id, xp, first_name, last_name in rows:
            display_name = f"{first_name} {last_name}".strip() or f"ID:{user_id}"
            html_name = f'<a href="tg://user?id={user_id}">{display_name}</a>'
            lines.append(f"{rank}. {html_name} ({city_name_display}) — {int(xp)} XP")
            rank += 1

    else:
        # Глобальный топ-N (по сумме XP во всех чатах)
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
        top_users = cur.fetchall()

        if not top_users:
            update.message.reply_text("Пока нет данных.", quote=True)
            conn.close()
            return

        lines.append(f"🏆 Глобальный топ-{n}:")
        rank = 1
        for user_id, sum_xp in top_users:
            # Находим, в каком чате у этого пользователя самый высокий XP
            cur.execute(
                "SELECT chat_id FROM xp WHERE user_id = ? ORDER BY total_xp DESC LIMIT 1",
                (user_id,)
            )
            top_chat_row = cur.fetchone()
            chat_name = get_city_name(top_chat_row[0]) if top_chat_row else "Неизвестно"

            # Берём имя из любой записи
            cur.execute(
                "SELECT first_name, last_name FROM xp WHERE user_id = ? LIMIT 1",
                (user_id,)
            )
            name_row = cur.fetchone()
            first_name, last_name = name_row if name_row else ("", "")
            display_name = f"{first_name} {last_name}".strip() or f"ID:{user_id}"
            html_name = f'<a href="tg://user?id={user_id}">{display_name}</a>'

            lines.append(f"{rank}. {html_name} ({chat_name}) — {int(sum_xp)} XP")
            rank += 1

    conn.close()
    update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# ==============================================================================
# КОМАНДА /rank — ЛИЧНЫЙ РЕЙТИНГ (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

def cmd_rank(update: Update, context: CallbackContext):
    """
    /rank [<город>]
    - Если указан <город>, показывает ваши XP и уровень в этом чате.
    - Иначе показывает суммарный (глобальный) XP по всем чатам.
    Работает только в личке и только для админов (ALLOWED_USER_IDS).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    args = context.args
    city_map = {city["name"].lower(): city["chat_id"] for city in ALL_CITIES}

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    if args:
        city_name = " ".join(args).lower()
        if city_name not in city_map:
            update.message.reply_text(
                f"Город «{' '.join(args)}» не найден. Доступные: {', '.join(city_map.keys())}.",
                quote=True
            )
            conn.close()
            return
        target_chat_id = city_map[city_name]

        cur.execute(
            "SELECT total_xp, first_name, last_name FROM xp WHERE chat_id = ? AND user_id = ?",
            (target_chat_id, user.id)
        )
        row = cur.fetchone()
        conn.close()

        if row:
            total, first_name, last_name = row
        else:
            total, first_name, last_name = 0.0, "", ""

        level = floor(sqrt(total))
        to_next = (level + 1) ** 2 - total
        display_name = f"{first_name} {last_name}".strip() or f"ID:{user.id}"
        city_display = city_name.title()

        text = (
            f"👤 {display_name}, ваши очки в «{city_display}»: {int(total)}\n"
            f"🎓 Уровень: {level} (до следующего уровня осталось {int(to_next)} XP)"
        )
        update.message.reply_text(text, quote=True)

    else:
        # Глобальный рейтинг
        cur.execute(
            "SELECT SUM(total_xp) FROM xp WHERE user_id = ?",
            (user.id,)
        )
        row = cur.fetchone()
        total = row[0] if row and row[0] is not None else 0.0

        level = floor(sqrt(total))
        to_next = (level + 1) ** 2 - total

        # Берём имя из первой записи
        cur.execute(
            "SELECT first_name, last_name FROM xp WHERE user_id = ? LIMIT 1",
            (user.id,)
        )
        name_row = cur.fetchone()
        conn.close()

        if name_row:
            first_name, last_name = name_row
        else:
            first_name, last_name = "", ""
        display_name = f"{first_name} {last_name}".strip() or f"ID:{user.id}"

        text = (
            f"👤 {display_name}, ваши суммарные очки по всем городам: {int(total)}\n"
            f"🎓 Уровень: {level} (до следующего уровня осталось {int(to_next)} XP)"
        )
        update.message.reply_text(text, quote=True)

# ==============================================================================
# КОМАНДА /dbdump — ПРОВЕРКА СОДЕРЖИМОГО БАЗЫ (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

def cmd_dbdump(update: Update, context: CallbackContext):
    """
    /dbdump — вернуть первые 10 строк из таблицы xp (для проверки).
    Работает только в личном диалоге и только для админов (ALLOWED_USER_IDS).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT chat_id, user_id, total_xp, first_name, last_name FROM xp LIMIT 10"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        update.message.reply_text("В базе пока нет ни одной записи.", quote=True)
        return

    lines = ["<b>Первые 10 строк из таблицы xp:</b>"]
    for chat_id, user_id, total_xp, first_name, last_name in rows:
        name = f"{first_name} {last_name}".strip() or f"ID:{user_id}"
        city = get_city_name(chat_id)
        lines.append(f"• {name} ({chat_id}, «{city}») — {int(total_xp)} XP")

    text = "\n".join(lines)
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==============================================================================
# КОМАНДА /dbpath — ПОКАЗАТЬ ПУТЬ К ФАЙЛУ БД (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

def cmd_dbpath(update: Update, context: CallbackContext):
    """
    /dbpath — вернёт абсолютный путь к файлу activity.db.
    Работает только в личном диалоге и только для админов (ALLOWED_USER_IDS).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    path = os.path.abspath(DB_PATH)
    update.message.reply_text(f"Файл базы находится здесь:\n`{path}`", parse_mode=ParseMode.MARKDOWN)

# ==============================================================================
# КОМАНДА /senddb — ОТПРАВИТЬ САМ ФАЙЛ activity.db (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

def cmd_senddb(update: Update, context: CallbackContext):
    """
    /senddb — бот пришлёт вам файл activity.db в личном чате.
    Работает только в личке и только для админов.
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    # Открываем файл в бинарном режиме и сразу передаём его методу reply_document
    try:
        with open(DB_PATH, "rb") as db_file:
            update.message.reply_document(document=db_file, filename="activity.db")
    except Exception as e:
        update.message.reply_text(f"Не удалось отправить файл: {e}", quote=True)

# ==============================================================================
# ХЭНДЛЕРЫ МЕНЮ И РАССЫЛОК (личный диалог, только ALLOWED_USER_IDS)
# ==============================================================================

user_buffers = {}
user_waiting = {}
user_mode = {}

def main_menu_keyboard(uid: int) -> ReplyKeyboardMarkup:
    """
    Формирует клавиатуру меню в личном чате у админа:
      - Тестовая рассылка (только для YOUR_ID)
      - Рассылка по городам
      - Список чатов ФАБА
      - Рейтинг
    """
    kb = [
        ["Рассылка по городам"],
        ["Список чатов ФАБА"],
        ["Рейтинг"]
    ]
    if uid == YOUR_ID:
        kb.insert(0, ["Тестовая рассылка"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

def menu(update: Update, context: CallbackContext):
    """
    /menu — открыть главное меню (личный диалог, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    update.message.reply_text("Выберите действие:", reply_markup=main_menu_keyboard(user.id))

def start_test_broadcast(update: Update, context: CallbackContext):
    """
    Режим тестовой рассылки (личный диалог, только YOUR_ID).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id != YOUR_ID:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "test"
    update.message.reply_text(
        "Отправляйте любые сообщения (текст, фото, стикеры и т. д.).\n"
        "Когда закончите, напишите /sendall."
    )

def start_city_broadcast(update: Update, context: CallbackContext):
    """
    Режим рассылки по городам (личный диалог, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    user_buffers[user.id] = []
    user_waiting[user.id] = True
    user_mode[user.id] = "city"
    update.message.reply_text(
        "Отправляйте любые сообщения для рассылки по всем городам.\n"
        "Когда закончите, напишите /sendall."
    )

def send_chat_list(update: Update, context: CallbackContext):
    """
    Показывает список всех чатов ФАБА (личный диалог, только админы).
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
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=markup
    )

def handle_back(update: Update, context: CallbackContext):
    """
    Кнопка «Назад» возвращает к главному меню (личный диалог, только админы).
    """
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private" or user.id not in ALLOWED_USER_IDS:
        return

    update.message.reply_text("Выберите действие:", reply_markup=main_menu_keyboard(user.id))

def add_to_buffer(update: Update, context: CallbackContext):
    """
    Добавляет сообщение в буфер для рассылки (личный диалог, только админы, если открыт буфер).
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
            "Сообщение добавлено к рассылке.\n"
            "Когда закончите — напишите /sendall, и рассылка уйдет."
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
                logging.error(f"Ошибка при рассылке: {e}")

    update.message.reply_text("Рассылка завершена.\nЧтобы начать заново, нажмите /menu")
    user_buffers[user.id] = []
    user_waiting[user.id] = False
    user_mode[user.id] = None

# ==============================================================================
# РЕГИСТРАЦИЯ ХЭНДЛЕРОВ
# ==============================================================================

# 1) Запись XP (во всех чатах из ALL_CITIES, кроме команд)
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

# 2) /top (личный диалог, только ALLOWED_USER_IDS)
dispatcher.add_handler(CommandHandler("top", cmd_top), group=2)

# 3) /rank (личный диалог, только ALLOWED_USER_IDS)
dispatcher.add_handler(CommandHandler("rank", cmd_rank), group=2)

# 4) /dbdump (личный диалог, только ALLOWED_USER_IDS) — для проверки содержимого БД
dispatcher.add_handler(CommandHandler("dbdump", cmd_dbdump), group=2)

# 5) /dbpath (личный диалог, только ALLOWED_USER_IDS) — показать путь к activity.db
dispatcher.add_handler(CommandHandler("dbpath", cmd_dbpath), group=2)

# 6) /senddb (личный диалог, только ALLOWED_USER_IDS) — прислать сам файл activity.db
dispatcher.add_handler(CommandHandler("senddb", cmd_senddb), group=2)

# 7) Меню и рассылки
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

# 8) Кнопка «Рейтинг» — ловим точное текстовое сообщение "Рейтинг" в личном чате и вызываем cmd_top
dispatcher.add_handler(
    MessageHandler(
        Filters.text("Рейтинг") & Filters.chat_type.private & Filters.user(ALLOWED_USER_IDS),
        cmd_top
    ),
    group=2
)

# ==============================================================================
# WEBHOOK-РУЧКА (быстрый ответ, фоновая обработка)
# ==============================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    threading.Thread(target=dispatcher.process_update, args=(update,)).start()
    return "OK", 200

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

# ==============================================================================
# УСТАНОВКА WEBHOOK (автоматически при импорте модуля)
# ==============================================================================

try:
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"Webhook установлен: {WEBHOOK_URL}/webhook")
except Exception as e:
    logger.error(f"Не удалось установить webhook: {e}")

# ==============================================================================
# ЛОКАЛЬНЫЙ ЗАПУСК (для отладки)
# ==============================================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
