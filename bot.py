import os
import time
import logging
import asyncio
import re
import nest_asyncio
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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например, "https://your-app.onrender.com"

if not BOT_TOKEN:
    raise ValueError("Не указан токен бота (BOT_TOKEN)")
if not WEBHOOK_URL:
    raise ValueError("Не указан URL для вебхука (WEBHOOK_URL)")

# Здесь можно определить ваши другие настройки (списки разрешённых пользователей, мэппинг чатов и т.п.)
ALLOWED_USER_IDS = [296920330, 320303183, 533773, 327650534, 136737738, 1283190854, 1607945564]
forwarded_messages = {}  # Глобальный словарь для хранения пересланных сообщений

# Создаем объект Request для бота
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

### Обработчик команды /edit

def edit_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS:
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

# Добавляем обработчик команды /edit
dispatcher.add_handler(CommandHandler("edit", edit_message, pass_args=True))

### Прочие обработчики
# (Пример: обработчик /menu, forward_message и т.п. – они остаются без изменений)
def menu(update: Update, context: CallbackContext):
    if update.message.from_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return
    keyboard = [["Написать сообщение", "Список чатов"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

def forward_message(update: Update, context: CallbackContext):
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
    # Здесь должна быть логика отправки сообщения в выбранные чаты
    # После успешной отправки сохраните идентификаторы пересланных сообщений:
    # forwarded_messages[update.message.message_id] = forwarded
    update.message.reply_text(f"Сообщение отправлено в: {selected_option}")
    context.user_data.pop("selected_chats", None)
    context.user_data.pop("selected_option", None)

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))

### Flask-приложение для вебхука

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
