import os
import time
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.request import Request

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Пример: "https://your-app.onrender.com"

if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# Список ID групп (групповые чаты должны иметь ID вида -100XXXXXXXXXX)
TARGET_CHATS = [
    -1002584369534,  # Замени на ID первой группы
    -1002596576819,  # Замени на ID второй группы
]

# Список ID пользователей, которым разрешено писать сообщения боту
ALLOWED_USER_IDS = [296920330, 320303183]  # Добавляй сюда другие ID, если нужно

# Глобальный словарь для хранения пересланных сообщений.
# Ключ: ID исходного сообщения, значение: словарь {chat_id: forwarded_message_id}
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

# Инициализация бота и диспетчера с несколькими рабочими потоками
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)  # workers > 0 для асинхронной обработки

# Обработчик команды /start
def start(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    update.message.reply_text("Привет! Отправь мне сообщение, и я перешлю его в группы.")

# Обработчик команды /publish_directory (пример для другой функции)
def publish_directory(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    update.message.reply_text("Команда publish_directory вызвана.")

# Обработчик входящих текстовых сообщений для пересылки
def forward_message(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для отправки сообщений.")
        return
    if update.message and update.message.text:
        msg_text = update.message.text
        update.message.reply_text("Сообщение поставлено в очередь отправки в группы!")
        forwarded = {}
        for chat_id in TARGET_CHATS:
            logging.info(f"Попытка отправить сообщение в чат {chat_id}: {msg_text}")
            sent_message = send_message_with_retry(chat_id, msg_text)
            if sent_message:
                forwarded[chat_id] = sent_message.message_id
            else:
                logging.error(f"Не удалось отправить сообщение в чат {chat_id} после повторных попыток.")
        if forwarded:
            forwarded_messages[update.message.message_id] = forwarded

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("publish_directory", publish_directory))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))

# Обработчик команды /edit для редактирования пересланного сообщения
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

# Временный обработчик для получения ID чата (для отладки)
def get_chat_id(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    update.message.reply_text(f"ID этой группы: {chat_id}")
    logging.info(f"ID группы: {chat_id}")

dispatcher.add_handler(CommandHandler("getid", get_chat_id))

# Создаем Flask-приложение
app = Flask(__name__)

# Маршрут для приема вебхуков от Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    logging.info(f"Получено обновление: {json_data}")
    update = Update.de_json(json_data, bot)
    dispatcher.process_update(update)
    return "OK", 200

# Маршрут для проверки работы сервиса
@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Запуск Flask-сервера на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
