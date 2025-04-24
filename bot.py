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
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 1607945564]

# Глобальный словарь для хранения пересланных сообщений
forwarded_messages = {}

# Для удобства создадим lookup-систему: chat_id -> название
city_lookup = {city["chat_id"]: city["name"] for city in ALL_CITIES}

# --- СОЗДАЁМ БОТА И ДИСПЕТЧЕР ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- ФУНКЦИЯ РАЗБОРА caption_entities ---
def rebuild_caption_with_entities(update: Update) -> str:
    """Преобразует caption и caption_entities в HTML-строку."""
    if not update.message.caption:
        return ""
    text = update.message.caption
    entities = update.message.caption_entities or []
    chars = list(text)
    for ent in sorted(entities, key=lambda e: e.offset + e.length, reverse=True):
        start = ent.offset
        end = ent.offset + ent.length
        if ent.type == "bold":
            chars.insert(end, "</b>")
            chars.insert(start, "<b>")
        elif ent.type == "italic":
            chars.insert(end, "</i>")
            chars.insert(start, "<i>")
        elif ent.type == "underline":
            chars.insert(end, "</u>")
            chars.insert(start, "<u>")
        elif ent.type == "strikethrough":
            chars.insert(end, "</s>")
            chars.insert(start, "<s>")
        elif ent.type == "code":
            chars.insert(end, "</code>")
            chars.insert(start, "<code>")
        elif ent.type == "spoiler":
            # Нативного <spoiler> нет – используем <u> как пример
            chars.insert(end, "</u>")
            chars.insert(start, "<u>")
    return "".join(chars)

# --- ФУНКЦИЯ ОТПРАВКИ С ПОВТОРНЫМИ ПОПЫТКАМИ ---
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    attempt = 1
    while attempt <= max_attempts:
        try:
            sent_message = bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML")
            logging.info(f"Сообщение отправлено в чат {chat_id}, message_id={sent_message.message_id}")
            return sent_message
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке текста в {chat_id}: {e}")
            if "Chat not found" in str(e):
                return None
            attempt += 1
            time.sleep(delay)
    return None

# --- ФУНКЦИЯ ПЕРЕСЫЛКИ МЕДИА ---
def forward_multimedia(update: Update, chat_id):
    new_caption = rebuild_caption_with_entities(update)
    logging.info("Вызов forward_multimedia, проверяем тип медиа...")
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        logging.info(f"Отправляю фото в {chat_id}, file_id={photo_id}, caption='{new_caption}'")
        try:
            return bot.send_photo(chat_id=chat_id, photo=photo_id, caption=new_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")
            return None
    elif update.message.video:
        video_id = update.message.video.file_id
        logging.info(f"Отправляю видео в {chat_id}, file_id={video_id}, caption='{new_caption}'")
        try:
            return bot.send_video(chat_id=chat_id, video=video_id, caption=new_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка при отправке видео: {e}")
            return None
    elif update.message.audio:
        audio_id = update.message.audio.file_id
        logging.info(f"Отправляю аудио в {chat_id}, file_id={audio_id}, caption='{new_caption}'")
        try:
            return bot.send_audio(chat_id=chat_id, audio=audio_id, caption=new_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка при отправке аудио: {e}")
            return None
    elif update.message.document:
        doc_id = update.message.document.file_id
        logging.info(f"Отправляю документ в {chat_id}, file_id={doc_id}, caption='{new_caption}'")
        try:
            return bot.send_document(chat_id=chat_id, document=doc_id, caption=new_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка при отправке документа: {e}")
            return None
    else:
        logging.info("Медиа не обнаружено, отсылаем как текст.")
        return send_message_with_retry(chat_id, update.message.text)

# --- ГЛАВНОЕ МЕНЮ (/menu) ---
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    keyboard = [
        ["Список чатов ФАБА", "Отправить сообщение во все чаты ФАБА"],
        ["Тестовая отправка"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- ОБРАБОТКА МЕНЮ (group=0) ---
def handle_main_menu(update: Update, context: CallbackContext) -> bool:
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return False
    text = update.message.text.strip()
    logging.info(f"handle_main_menu: text='{text}'")
    if "pending_main_menu" not in context.user_data:
        return False

    if text == "Назад":
        logging.info("Пользователь выбрал 'Назад', возвращаемся в главное меню.")
        menu(update, context)
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    if text == "Список чатов ФАБА":
        info_lines = ["Список чатов ФАБА:"]
        for city in ALL_CITIES:
            try:
                if city["link"]:
                    info_lines.append(f"<a href='{city['link']}'>{city['name']}</a>")
                else:
                    info_lines.append(city["name"])
            except Exception as e:
                logging.error(f"Ошибка при обработке города {city['name']}: {e}")
                info_lines.append(f"{city['name']} - информация недоступна")
        back_markup = ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text("\n".join(info_lines),
                                  parse_mode="HTML",
                                  disable_web_page_preview=True,
                                  reply_markup=back_markup)
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    if text == "Отправить сообщение во все чаты ФАБА":
        chat_ids = [city["chat_id"] for city in ALL_CITIES]
        context.user_data["selected_chats"] = chat_ids
        context.user_data["selected_option"] = "Все чаты ФАБА"
        update.message.reply_text(
            "Вы выбрали: Отправить сообщение во все чаты ФАБА. Теперь отправьте сообщение.\nНажмите /menu для повторного выбора."
        )
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    if text == "Тестовая отправка":
        context.user_data["pending_test"] = True
        update.message.reply_text("Введите ваш текст (или фото, видео) для тестовой отправки.")
        context.user_data.pop("pending_main_menu", None)
        raise DispatcherHandlerStop

    update.message.reply_text("Неверный выбор. Используйте /menu для повторного выбора.")
    context.user_data.pop("pending_main_menu", None)
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, handle_main_menu),
    group=0
)

# --- ПЕРЕСЫЛКА СООБЩЕНИЙ (group=1) ---
def forward_message(update: Update, context: CallbackContext):
    msg = update.message
    if not msg or msg.chat.type != "private":
        return

    # === Тестовая отправка любых сообщений ===
    if context.user_data.get("pending_test"):
        # снимаем флаг, чтобы не зациклиться
        context.user_data.pop("pending_test", None)

        failures = []
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(
                    chat_id=cid,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
                logging.info(f"Тестовая отправка: скопировано сообщение {msg.message_id} → чат {cid}")
            except Exception as e:
                logging.error(f"Тестовая отправка: не удалось скопировать в {cid}: {e}")
                failures.append(cid)

        # Отвечаем пользователю
        if failures:
            failed_str = ", ".join(str(x) for x in failures)
            msg.reply_text(f"Часть тестовых сообщений не отправлены в: {failed_str}\nНажмите /menu для повторного выбора.")
        else:
            msg.reply_text("Тестовое сообщение успешно отправлено во все тестовые чаты.\nНажмите /menu для повторного выбора.")
        return

    # === Отправка в выбранные чаты ФАБА ===
    chat_ids = context.user_data.get("selected_chats", [])
    if not chat_ids:
        msg.reply_text("Сначала выберите действие, используя команду /menu.")
        return

    failures = []
    for cid in chat_ids:
        try:
            bot.copy_message(
                chat_id=cid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
            logging.info(f"Скопировано сообщение {msg.message_id} → чат {cid}")
        except Exception as e:
            logging.error(f"Не удалось скопировать сообщение в чат {cid}: {e}")
            failures.append(cid)

    if failures:
        failed_str = ", ".join(str(x) for x in failures)
        msg.reply_text(f"Часть сообщений отправлена, но не получилось в: {failed_str}\nНажмите /menu для нового выбора.")
    else:
        msg.reply_text("Сообщение успешно доставлено во все чаты.\nНажмите /menu для нового выбора.")

    # чистим состояние
    context.user_data.pop("selected_chats", None)
    context.user_data.pop("selected_option", None)

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & ~Filters.command, forward_message),
    group=1
)

# --- /edit, /delete, /getid ---
def edit_message(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для редактирования сообщений.")
        return
    if not update.message.reply_to_message:
        update.message.reply_text("Используйте команду /edit, ответив на пересланное сообщение, которое хотите отредактировать.")
        return
    original_id = update.message.reply_to_message.message_id
    new_text = ' '.join(context.args)
    if not new_text:
        update.message.reply_text("Укажите новый текст для редактирования.")
        return
    if original_id not in forwarded_messages:
        update.message.reply_text("Не найдены пересланные сообщения для редактирования.")
        return
    edits = forwarded_messages[original_id]
    success = True
    for chat_id, fwd_msg_id in edits.items():
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=fwd_msg_id, text=new_text, parse_mode="HTML")
            logging.info(f"Сообщение в {chat_id} отредактировано, message_id={fwd_msg_id}")
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения в {chat_id}: {e}")
            success = False
    if success:
        update.message.reply_text("Сообщения отредактированы.\nНажмите /menu для повторного выбора.")
    else:
        update.message.reply_text("Ошибка при редактировании некоторых сообщений.\nНажмите /menu для повторного выбора.")

dispatcher.add_handler(CommandHandler("edit", edit_message, pass_args=True))

def delete_message(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для удаления сообщений.")
        return
    if not update.message.reply_to_message:
        update.message.reply_text("Используйте команду /delete, ответив на пересланное сообщение, которое хотите удалить.")
        return
    original_id = update.message.reply_to_message.message_id
    if original_id not in forwarded_messages:
        update.message.reply_text("Не найдены пересланные сообщения для удаления.")
        return
    deletions = forwarded_messages[original_id]
    success = True
    for chat_id, fwd_msg_id in deletions.items():
        try:
            bot.delete_message(chat_id=chat_id, message_id=fwd_msg_id)
            logging.info(f"Сообщение в {chat_id} удалено, message_id={fwd_msg_id}")
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения в {chat_id}: {e}")
            success = False
    if success:
        update.message.reply_text("Сообщения удалены.\nНажмите /menu для повторного выбора.")
    else:
        update.message.reply_text("Ошибка при удалении некоторых сообщений.\nНажмите /menu для повторного выбора.")
    forwarded_messages.pop(original_id, None)

dispatcher.add_handler(CommandHandler("delete", delete_message))

def get_chat_id(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    update.message.reply_text(f"ID этой группы: {chat_id}")
    logging.info(f"ID группы: {chat_id}")

dispatcher.add_handler(CommandHandler("getid", get_chat_id))

# --- Flask-приложение и вебхук ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    logging.info(f"Получено обновление: {json_data}")
    update = Update.de_json(json_data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Запуск Flask-сервера на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
