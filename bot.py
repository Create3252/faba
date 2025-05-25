import os
import logging
from flask import Flask, request
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    DispatcherHandlerStop,
)
from telegram.utils.request import Request

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Не указан BOT_TOKEN или WEBHOOK_URL")

# --- Тестовые чаты ---
TEST_SEND_CHATS = [
    -1002596576819,  # Москва тест
    -1002584369534   # Тюмень тест
]
ALLOWED_USER_IDS = {296920330, 320303183, 533773, 327650534, 533007308, 136737738, 1607945564}

# --- Инициализация ---
req = Request(connect_timeout=20, read_timeout=20)
bot = Bot(token=BOT_TOKEN, request=req)
dispatcher = Dispatcher(bot, None, workers=4)

# --- Команда /menu ---
def menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    kb = [["Тестовая рассылка"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Выберите действие:", reply_markup=markup)
    context.user_data.clear()
    context.user_data["pending_main_menu"] = True

dispatcher.add_handler(CommandHandler("menu", menu))

# --- Обработка выбора в меню ---
def handle_main_menu(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS or not context.user_data.get("pending_main_menu"):
        return
    choice = update.message.text.strip()
    context.user_data.pop("pending_main_menu", None)
    if choice == "Тестовая рассылка":
        context.user_data["mass_send"] = True
        context.user_data["to_send"] = []
        update.message.reply_text(
            "Отправляй любые сообщения (текст, фото, кружки и т.д.). Когда закончишь — напиши /sendall."
        )
        raise DispatcherHandlerStop
    update.message.reply_text("Неверный выбор. /menu")
    raise DispatcherHandlerStop

dispatcher.add_handler(
    MessageHandler(Filters.chat_type.private & Filters.text, handle_main_menu),
    group=0
)

# --- Сбор сообщений для рассылки ---
def collect_for_mass_send(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return
    # если режим массовой рассылки
    if context.user_data.get("mass_send"):
        # добавляем объект сообщения в список для рассылки
        context.user_data["to_send"].append(update.message)
        update.message.reply_text("Сообщение добавлено к рассылке. Когда закончите — напишите /sendall.")

dispatcher.add_handler(
    MessageHandler(
        Filters.chat_type.private &
        (Filters.text | Filters.photo | Filters.video | Filters.audio | Filters.document | Filters.voice | Filters.video_note)
        & ~Filters.command,  # не команды!
        collect_for_mass_send
    ),
    group=1
)

# --- Пересылка всех собранных сообщений по команде /sendall ---
def send_all(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    if uid not in ALLOWED_USER_IDS:
        return update.message.reply_text("У вас нет прав.")
    if not context.user_data.get("mass_send") or not context.user_data.get("to_send"):
        return update.message.reply_text("Нет сообщений для рассылки.")
    msgs = context.user_data.pop("to_send")
    for msg in msgs:
        for cid in TEST_SEND_CHATS:
            try:
                bot.copy_message(chat_id=cid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка пересылки в {cid}: {e}")
    context.user_data["mass_send"] = False
    update.message.reply_text("Готово! Все сообщения отправлены.")

dispatcher.add_handler(CommandHandler("sendall", send_all))

# --- Flask и Webhook ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    return "Bot is running", 200

if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
