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

# Инициализация бота и диспетчера
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=0)

# Обработчики команд и сообщений
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Я бот по вебхукам.")

def publish_directory(update: Update, context: CallbackContext):
    update.message.reply_text("Команда publish_directory вызвана.")

def forward_message(update: Update, context: CallbackContext):
    if update.message and update.message.text:
        update.message.reply_text("Сообщение получено.")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("publish_directory", publish_directory))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))

# Создаем Flask-приложение
app = Flask(__name__)

# Маршрут для приема вебхуков от Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
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
