import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, "https://your-app.onrender.com"

if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# Список ID групп (групповые чаты должны иметь ID вида -100XXXXXXXXXX)
TARGET_CHATS = [
    -1002584369534,  # Чат Тюмени
    -1002596576819,  # Чат Москвы
]

# Маппинг для выбора чатов (для отправки сообщений)
CHAT_OPTIONS = {
    "Тюмень": [TARGET_CHATS[0]],
    "Москва": [TARGET_CHATS[1]],
    "Оба": TARGET_CHATS
}

# Список ID пользователей, которым разрешено использовать бота
ALLOWED_USER_IDS = [296920330, 320303183]  # Добавьте нужные ID

# Глобальный словарь для хранения пересланных сообщений.
# Ключ: ID исходного сообщения (в личном чате), значение: словарь {chat_id: forwarded_message_id}
forwarded_messages = {}

# Функция для отправки сообщения с повторными попытками
def send_message_with_retry(chat_id, msg_text, max_attempts=3, delay=5):
    attempt = 1
    while attempt <= max_attempts:
        try:
            sent_message = bot.send_message(chat_id=chat_id, text=msg_text)
            logging.info(f"Сообщение отправлено в чат {chat_id}, message_id: {sent_message.message_id}")
            return sent_message
        except Exception as e:
            logging.error(f"Попытка {attempt}: ошибка при отправке сообщения в чат {chat_id}: {e}")
            attempt += 1
            time.sleep(delay)
    return None

# Инициализация бота и диспетчера
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

### Главное меню и обработчики выбора

# Команда /menu – выводит главное меню с двумя кнопками
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    keyboard = [["Написать сообщение", "Список чатов"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# Обработчик выбора в главном меню
def handle_main_menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return
    if "pending_main_menu" not in context.user_data:
        return

    choice = update.message.text.strip()
    if choice == "Написать сообщение":
        # Выводим клавиатуру для выбора чатов
        keyboard = [["Тюмень", "Москва"], ["Оба"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text("Выберите, куда отправлять сообщение:", reply_markup=reply_markup)
        context.user_data["pending_destination"] = True

    elif choice == "Список чатов":
    info_lines = ["Список чатов ФАБА:"]
    # Список ID, которых не учитываем при подсчёте
    ignore_ids = [
        296920330, 7905869507, 320303183,
        533773, 327650534, 136737738, 1283190854, 1607945564
    ]
    for chat_id in TARGET_CHATS:
        try:
            chat_info = bot.get_chat(chat_id)
            # Используем get_chat_member_count вместо устаревшего get_chat_members_count
            count = bot.get_chat_member_count(chat_id)

            # Вычитаем пользователей из ignore_ids, если они присутствуют
            for ignore_id in ignore_ids:
                try:
                    member = bot.get_chat_member(chat_id, ignore_id)
                    if member.status not in ["left", "kicked"]:
                        count -= 1
                except Exception as e:
                    # Если ошибка participant_id_invalid, пропускаем
                    if "Participant_id_invalid" in str(e):
                        continue
                    else:
                        logging.error(f"Ошибка при проверке пользователя {ignore_id} для чата {chat_id}: {e}")

            # Формируем кликабельную ссылку, если есть публичный username
            if chat_info.username:
                link = f"https://t.me/{chat_info.username}"
                info_lines.append(f"<a href='{link}'>{chat_info.title}</a> — количество членов: {count}")
            else:
                info_lines.append(f"{chat_info.title} — количество членов: {count}")

        except Exception as e:
            logging.error(f"Ошибка при получении информации для чата {chat_id}: {e}")
            info_lines.append("Информация для чата недоступна.")

    # Отправляем одним сообщением
    update.message.reply_text(
        "\n".join(info_lines),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
        )

    else:
        update.message.reply_text("Неверный выбор. Используйте /menu для повторного выбора.")

    context.user_data.pop("pending_main_menu", None)

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex("^(Написать сообщение|Список чатов)$"), handle_main_menu))

# Обработчик для выбора чатов (после выбора "Написать сообщение")
def handle_destination_choice(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        return
    if "pending_destination" not in context.user_data:
        return

    choice = update.message.text.strip()
    if choice in CHAT_OPTIONS:
        context.user_data["selected_chats"] = CHAT_OPTIONS[choice]
        context.user_data["selected_option"] = choice
        update.message.reply_text(f"Вы выбрали: {choice}. Теперь отправьте сообщение.")
    else:
        update.message.reply_text("Неверный выбор. Используйте /choose для повторного выбора.")

    context.user_data.pop("pending_destination", None)

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex("^(Тюмень|Москва|Оба)$"), handle_destination_choice))

### Отправка сообщения

def forward_message(update: Update, context: CallbackContext):
    # Обработка только личных сообщений
    if update.message.chat.type != "private":
        return
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для отправки сообщений.")
        return
    if "selected_chats" not in context.user_data:
        update.message.reply_text("Сначала выберите действие, используя команду /menu.")
        return

    msg_text = update.message.text
    selected_option = context.user_data.get("selected_option", "неизвестно")
    update.message.reply_text("Сообщение поставлено в очередь отправки!")
    forwarded = {}
    for chat_id in context.user_data["selected_chats"]:
        logging.info(f"Попытка отправить сообщение в чат {chat_id}: {msg_text}")
        sent_message = send_message_with_retry(chat_id, msg_text)
        if sent_message:
            forwarded[chat_id] = sent_message.message_id
        else:
            logging.error(f"Не удалось отправить сообщение в чат {chat_id} после повторных попыток.")
    if forwarded:
        forwarded_messages[update.message.message_id] = forwarded
        update.message.reply_text(f"Сообщение отправлено в: {selected_option}")
    context.user_data.pop("selected_chats", None)
    context.user_data.pop("selected_option", None)

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))

### Редактирование пересланных сообщений

def edit_message(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для редактирования сообщений.")
        return
    if not update.message.reply_to_message:
        update.message.reply_text("Используйте команду /edit, ответив на исходное сообщение, которое хотите отредактировать.")
        return

    original_id = update.message.reply_to_message.message_id
    new_text = ' '.join(context.args)
    if not new_text:
        update.message.reply_text("Укажите новый текст для редактирования.")
        return
    if original_id not in forwarded_messages:
        update.message.reply_text("Не найдены пересланные сообщения для редактирования. Убедитесь, что вы отвечаете на правильное сообщение.")
        return

    edits = forwarded_messages[original_id]
    success = True
    for chat_id, fwd_msg_id in edits.items():
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=fwd_msg_id, text=new_text)
            logging.info(f"Сообщение в чате {chat_id} отредактировано, message_id: {fwd_msg_id}")
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения в чате {chat_id}: {e}")
            success = False
    if success:
        update.message.reply_text("Сообщения отредактированы.")
    else:
        update.message.reply_text("Произошла ошибка при редактировании некоторых сообщений.")

dispatcher.add_handler(CommandHandler("edit", edit_message, pass_args=True))

### Дополнительный обработчик для отладки

def get_chat_id(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    update.message.reply_text(f"ID этой группы: {chat_id}")
    logging.info(f"ID группы: {chat_id}")

dispatcher.add_handler(CommandHandler("getid", get_chat_id))

### Flask-приложение и вебхук

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    logging.info(f"Получено обновление: {json_data}")
    update = Update.de_json(json_data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Запуск Flask-сервера на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
