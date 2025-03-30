import os
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

# Инициализация бота и диспетчера с несколькими рабочими потоками
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)  # workers > 0 для асинхронной обработки

# Обработчик команды /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Отправь мне сообщение, и я перешлю его в группы.")

# Обработчик команды /publish_directory (пример для другой функции)
def publish_directory(update: Update, context: CallbackContext):
    update.message.reply_text("Команда publish_directory вызвана.")

# Обработчик входящих текстовых сообщений
def forward_message(update: Update, context: CallbackContext):
    if update.message and update.message.text:
        msg_text = update.message.text
        update.message.reply_text("Сообщение отправлено в группы!")
        for chat_id in TARGET_CHATS:
            try:
                logging.info(f"Отправляю сообщение в чат {chat_id}: {msg_text}")
                context.bot.send_message(chat_id=chat_id, text=f"Пересланное сообщение: {msg_text}")
                logging.info(f"Сообщение отправлено в чат {chat_id}")
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("publish_directory", publish_directory))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))

# Добавляем временный обработчик для получения ID чата (для отладки)
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
    # Удаляем предыдущий вебхук (если есть) и устанавливаем новый
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    # Получаем порт из переменной окружения (Render задаёт PORT)
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Запуск Flask-сервера на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
