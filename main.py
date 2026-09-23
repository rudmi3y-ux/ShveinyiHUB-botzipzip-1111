#!/usr/bin/env python3
import os
import sys
import time
import asyncio
import threading
import json
import socket
import atexit
import logging
from dotenv import load_dotenv

# Принудительно загружаем .env, чтобы игнорировать старые токены хостинга
load_dotenv(override=True)

# --- ИМПОРТ ВЕБ-АДМИНКИ ---
# Если папка называется webapp и файл app.py, то импорт такой:
try:
    from webapp.app import app
except ImportError:
    # Заглушка на случай, если структура файлов другая, чтобы бот не упал
    from flask import Flask
    app = Flask(__name__)

    @app.route('/')
    def index():
        return "Ошибка импорта webapp.app. Проверьте структуру папок."


from telegram import Update, MenuButtonCommands, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          CallbackQueryHandler, MessageHandler,
                          ConversationHandler, filters, TypeHandler, ContextTypes)

from handlers import commands, messages, admin
from handlers.commands import faq_command, status_command

# --- ИМПОРТЫ ЗАКАЗОВ ---
from handlers.orders import (
    order_start, select_service, receive_photo, skip_photo, enter_name,
    enter_phone, confirm_order, cancel_order, use_tg_name, skip_phone as
    skip_phone_handler, handle_order_status_change, enter_description,
    skip_description, ENTER_DESCRIPTION, SELECT_SERVICE, SEND_PHOTO,
    ENTER_NAME, ENTER_PHONE, CONFIRM_ORDER)
# ----------------------------

from handlers.reviews import get_review_conversation_handler, request_review
from keyboards import (get_main_menu, get_prices_menu, get_faq_menu,
                       get_back_button, get_admin_main_menu)
from utils.database import (init_db, get_user_orders,
                            get_orders_pending_feedback,
                            mark_feedback_requested)
from utils.prices import format_prices_text, import_prices_data

_lock = None
logger = logging.getLogger(__name__)


# --- БЛОКИРОВКА ПОВТОРНОГО ЗАПУСКА ---
def create_lock():
    global _lock
    if os.getenv("DISABLE_INSTANCE_LOCK", "0") == "1":
        return None
    lock_port = int(os.getenv("LOCK_PORT", "48975"))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", lock_port))
        s.listen(1)
        s.setblocking(False)
        _lock = {"type": "socket", "obj": s, "port": lock_port}
        return _lock
    except OSError:
        pass
    return None


def release_lock():
    global _lock
    try:
        if isinstance(_lock, dict) and _lock.get("type") == "socket":
            _lock["obj"].close()
    except Exception:
        pass
    finally:
        _lock = None


atexit.register(release_lock)

from handlers.admin_panel.handlers import set_admin_commands, show_admin_stats, show_spam_candidates, mark_as_spam_callback

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
BOT_START_TIME = time.time()
WORKSHOP_INFO = {
    "name": "Швейная мастерская",
    "address":
    "г. Москва, (МЦД/м. Ховрино) ул. Маршала Федоренко д.12, , ТЦ \"Бусиново\", 1 этаж",
    "phone": "+7 (968) 396-91-52",
    "whatsapp": "+7 (968) 396-91-52"
}

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)


# --- CALLBACK ФУНКЦИИ ---
async def callback_services(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text="💰 Выберите категорию услуг:", reply_markup=get_prices_menu())


async def callback_price_category(update, context, category):
    await update.callback_query.answer()
    prices_text = format_prices_text(category)
    if prices_text:
        await update.callback_query.edit_message_text(
            text=prices_text,
            reply_markup=get_prices_menu(),
            parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(
            text="Цены не найдены", reply_markup=get_prices_menu())


# Обертки для категорий цен
async def callback_price_jacket(update, context):
    await callback_price_category(update, context, "jacket")


async def callback_price_leather(update, context):
    await callback_price_category(update, context, "leather")


async def callback_price_curtains(update, context):
    await callback_price_category(update, context, "curtains")


async def callback_price_coat(update, context):
    await callback_price_category(update, context, "coat")


async def callback_price_fur(update, context):
    await callback_price_category(update, context, "fur")


async def callback_price_outerwear(update, context):
    await callback_price_category(update, context, "outerwear")


async def callback_price_pants(update, context):
    await callback_price_category(update, context, "pants")


async def callback_price_dress(update, context):
    await callback_price_category(update, context, "dress")


async def callback_check_status(update, context):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    orders = get_user_orders(user_id)
    if not orders:
        text = "🔍 У вас нет заказов.\n\nПозвоните нам: " + WORKSHOP_INFO[
            "phone"]
    else:
        from handlers.orders import format_order_id
        text = "🔍 *Ваши заказы:*\n\n"
        status_map = {
            "new": "🆕 Новый",
            "in_progress": "🔄 В работе",
            "completed": "✅ Готов",
            "issued": "📤 Выдан",
            "cancelled": "❌ Отменён"
        }
        for order in orders[:5]:
            status = status_map.get(str(order.status), str(order.status))
            desc = str(order.description) if order.description else "Услуга"
            formatted_id = format_order_id(int(order.id), order.created_at)
            text += f"*{formatted_id}* - {status}\n{desc}\n\n"
    await update.callback_query.edit_message_text(
        text=text, reply_markup=get_back_button(), parse_mode="Markdown")


# FAQ Callbacks
async def callback_faq(update, context):
    await update.callback_query.answer()
    try:
        await update.callback_query.edit_message_text(
            text="❓ Выберите интересующий вопрос:",
            reply_markup=get_faq_menu())
    except:
        pass


async def callback_faq_services(update, context):
    await update.callback_query.answer()
    text = "📋 *Какие услуги мы выполняем:*\n\n✂️ Подшив и укорачивание\n🔄 Замена молний и пуговиц\n📐 Ушивание и расширение\n🧥 Ремонт верхней одежды\n🎒 Ремонт кожаных изделий\n🐾 Ремонт шуб и дублёнок\n🪟 Пошив штор"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_prices(update, context):
    await update.callback_query.answer()
    text = "💰 *Примерные цены:*\n\n👖 Укоротить джинсы — от 500р\n👖 С родным краем — от 900р\n👗 Укоротить юбку — от 800р\n🧥 Замена молнии — от 2000р\n🧥 Замена подкладки — от 3500р\n📐 Подгон по фигуре — от 1500р"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_timing(update, context):
    await update.callback_query.answer()
    text = "⏰ *Сроки:*\n\n⚡ Простой ремонт — 1-2 дня\n📦 Сложный ремонт — 3-7 дней\n🚀 Срочный ремонт — 24 часа (+50%)"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_location(update, context):
    await update.callback_query.answer()
    text = f"📍 *Адрес:*\n{WORKSHOP_INFO['address']}\n\n⏰ *График:*\nПн-Чт: 10:00-19:50\nПт: 10:00-19:00\nСб: 10:00-17:00\nВс: выходной\n\n📞 {WORKSHOP_INFO['phone']}"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_payment(update, context):
    await update.callback_query.answer()
    text = "💳 *Способы оплаты:*\n• Наличные\n• Перевод по номеру\n\n💵 *Предоплата:*\nНе требуется для обычного ремонта\n50% — для дорогой фурнитуры\n\n🛡️ *Гарантия:*\n30 дней на все виды!"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_order(update, context):
    await update.callback_query.answer()
    text = "📝 *Как оформить:*\n\n1️⃣ Создать заказ\n2️⃣ Выберите услугу\n3️⃣ Фото вещи\n4️⃣ Имя и телефон\n5️⃣ Подтвердите\n\nМы свяжемся для уточнения!"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_faq_other(update, context):
    await update.callback_query.answer()
    text = f"❓ *Другой вопрос?*\n\nОпишите здесь в чате или позвоните: {WORKSHOP_INFO['phone']}"
    try:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=get_faq_menu(), parse_mode="Markdown")
    except:
        pass


async def callback_contacts(update, context):
    await update.callback_query.answer()
    hours_text = "Пн-Чт: 10:00-19:50\nПт: 10:00-19:00\nСб: 10:00-17:00\nВс: выходной"
    await update.callback_query.edit_message_text(
        text=
        f"📍 *Наши контакты:*\n\n📍 *Адрес:*\n{WORKSHOP_INFO['address']}\n\n📞 *Телефон:*\n{WORKSHOP_INFO['phone']}\n\n💬 *WhatsApp:*\n{WORKSHOP_INFO['whatsapp']}\n\n⏰ *График:*\n{hours_text}",
        reply_markup=get_back_button(),
        parse_mode="Markdown")


async def callback_back(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text="✂️ *Швейный HUB — Главное меню*",
        reply_markup=get_main_menu(),
        parse_mode="Markdown")


async def callback_contact_master(update, context):
    await update.callback_query.answer()
    text = f"👩‍🔧 *Связаться с мастером*\n\n📞 *Позвоните:* {WORKSHOP_INFO['phone']}\n💬 *WhatsApp:* {WORKSHOP_INFO['whatsapp']}\n\n📍 *Адрес:*\n{WORKSHOP_INFO['address']}\n\n⏰ Пн-Чт: 10:00-19:50\nПт: 10:00-19:00\nСб: 10:00-17:00"
    await update.callback_query.edit_message_text(
        text=text, reply_markup=get_back_button(), parse_mode="Markdown")


# Команды меню
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.jpg")


async def show_menu_with_logo(message, name):
    caption = f"✂️ *Швейный HUB*\n\nИголочка на связи! 🪡\nЧем могу помочь, {name}?"
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as photo:
            await message.reply_photo(photo=photo,
                                      caption=caption,
                                      parse_mode="Markdown")
    else:
        await message.reply_text(caption, parse_mode="Markdown")
    await message.reply_text("✂️ *Швейный HUB — Главное меню*",
                             reply_markup=get_main_menu(),
                             parse_mode="Markdown")


async def order_command(update, context):
    await order_start(update, context)


async def services_command(update, context):
    if update.message:
        await update.message.reply_text(text="💰 Выберите категорию услуг:",
                                        reply_markup=get_prices_menu())


async def contact_command(update, context):
    text = f"📍 *Контакты мастерской*\n\n🏠 *Адрес:* {WORKSHOP_INFO['address']}\n\n📞 *Телефон:* {WORKSHOP_INFO['phone']}\n💬 *WhatsApp:* {WORKSHOP_INFO['whatsapp']}\n\n⏰ *График:*\nПн-Чт: 10:00-19:50\nПт: 10:00-19:00\nСб: 10:00-17:00\nВс: выходной"
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")


async def menu_command(update, context):
    user = update.effective_user
    name = user.first_name or "друг"
    message = update.message or (update.callback_query.message
                                 if update.callback_query else None)
    if message: await show_menu_with_logo(message, name)


async def admin_panel_command(update, context):
    user_id = update.effective_user.id
    from handlers.admin import is_user_admin
    if not is_user_admin(user_id):
        if update.message:
            await update.message.reply_text(
                "⛔ У вас нет доступа к этой команде.")
        return
    text = "📋 *Админ-панель*\n\nВыберите раздел для управления:"
    if update.message:
        await update.message.reply_text(text,
                                        reply_markup=get_admin_main_menu(),
                                        parse_mode="Markdown")


async def log_all_updates(update: Update, context):
    user_id = update.effective_user.id if update.effective_user else "unknown"
    if update.callback_query:
        logger.info(f"📥 CALLBACK: {update.callback_query.data} from {user_id}")
    elif update.message:
        text = update.message.text[:50] if update.message.text else "[no text]"
        logger.info(f"📥 MESSAGE: {text} from {user_id}")


create_lock()
BOT_TOKEN = os.getenv("BOT_TOKEN")


# --- ГЛАВНАЯ ФУНКЦИЯ ---
def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return

    # Запускаем Flask веб-админки
    def run_flask():
        try:
            # В Replit 5000 - стандартный порт для webview. Используем альтернативный порт
            port = int(os.getenv("FLASK_PORT", "8080"))  # Use port 8080 as alternative
            app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
        except Exception as e:
            logger.error(f"Ошибка при запуске Flask: {e}")

    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Даем Flask время на запуск
    time.sleep(3)
    # -----------------------------------

    init_db()
    try:
        import_prices_data()
    except Exception:
        logger.warning("Не удалось загрузить цены")
    logger.info("База данных инициализирована")

    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start", "🏠 Главное меню"),
            BotCommand("order", "➕ Оформить заказ"),
            BotCommand("faq", "❓ FAQ"),
            BotCommand("status", "🔍 Статус заказа"),
            BotCommand("services", "📋 Услуги и цены"),
            BotCommand("contact", "📞 Контакты"),
            BotCommand("help", "❓ Справка"),
        ])
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonCommands())

        async def periodic_review_check():
            await asyncio.sleep(60)
            while True:
                try:
                    orders = get_orders_pending_feedback()
                    for order in orders:
                        try:
                            user_id = int(
                                order.user_id) if order.user_id else 0
                            order_id = int(order.id) if order.id else 0
                            await request_review(application, user_id,
                                                 order_id)
                            mark_feedback_requested(order_id)
                        except Exception as e:
                            logger.error(f"Failed review request: {e}")
                except Exception as e:
                    logger.error(f"Error checking reviews: {e}")
                await asyncio.sleep(3600)

        try:
            application.create_task(periodic_review_check())
        except Exception as e:
            logger.error(f"Не удалось запустить фоновую задачу: {e}")

    app_bot = ApplicationBuilder().token(BOT_TOKEN).post_init(
        post_init).build()
    app_bot.add_handler(TypeHandler(Update, log_all_updates), group=-1)

    order_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(order_start, pattern="^new_order$"),
            CommandHandler("order", order_start)
        ],
        states={
            SELECT_SERVICE: [
                CallbackQueryHandler(select_service, pattern="^service_"),
                CallbackQueryHandler(cancel_order, pattern="^back_menu$")
            ],
            SEND_PHOTO: [
                MessageHandler(filters.PHOTO, receive_photo),
                CallbackQueryHandler(skip_photo, pattern="^skip_photo$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               enter_description),
                CallbackQueryHandler(skip_description,
                                     pattern="^skip_description$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ],
            ENTER_NAME: [
                CallbackQueryHandler(use_tg_name, pattern="^use_tg_name$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ],
            ENTER_PHONE: [
                CallbackQueryHandler(skip_phone_handler,
                                     pattern="^skip_phone$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern="^confirm_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_order, pattern="^cancel_order$"),
            CommandHandler("cancel", lambda u, c: cancel_order(u, c))
        ],
        allow_reentry=True,
        per_message=False)


    # Broadcast handler (зарегистрирован в группе 0 ДО conversation'ов,
    # чтобы не перехватывать текстовый ввод в диалогах заказа/отзыва)
    async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Обрабатываем только текст; команды не трогаем
        if not update.message or not update.message.text:
            return
        from handlers.admin import is_user_admin, broadcast_send
        if not update.effective_user or not is_user_admin(update.effective_user.id):
            return

        if context.user_data.get("broadcast_mode"):
            if update.message.text == "/cancel":
                context.user_data["broadcast_mode"] = False
                await update.message.reply_text("❌ Рассылка отменена.")
                return

            await broadcast_send(update, context)
            context.user_data["broadcast_mode"] = False

    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_broadcast_message))

    app_bot.add_handler(order_conversation)
    app_bot.add_handler(get_review_conversation_handler())

    # Основные команды
    app_bot.add_handler(CommandHandler("start", commands.start))
    app_bot.add_handler(CommandHandler("help", commands.help_command))
    app_bot.add_handler(CommandHandler("faq", faq_command))
    app_bot.add_handler(CommandHandler("status", status_command))
    app_bot.add_handler(CommandHandler("services", services_command))
    app_bot.add_handler(CommandHandler("contact", contact_command))
    app_bot.add_handler(CommandHandler("menu", menu_command))

    # Текстовые кнопки админа
    from handlers.admin import admin_orders as admin_orders_list, admin_stats as admin_stats_info, admin_users as admin_users_list, admin_spam as admin_spam_logs, broadcast_start as admin_broadcast_start
    from handlers.admin_panel.handlers import show_spam_candidates, mark_as_spam_callback
    
    # Админ команды
    app_bot.add_handler(CommandHandler("admin", admin_panel_command))
    app_bot.add_handler(CommandHandler("stats", admin_stats_info))
    app_bot.add_handler(CommandHandler("orders", admin_orders_list))
    app_bot.add_handler(CommandHandler("users", admin_users_list))
    app_bot.add_handler(CommandHandler("spam", admin_spam_logs))
    app_bot.add_handler(CommandHandler("broadcast", admin_broadcast_start))
    app_bot.add_handler(CommandHandler("search", admin_orders_list)) # Позже добавим поиск

    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📈 Статистика$"), admin_stats_info))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📊 Все заказы$"), admin_orders_list))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^❌ Удалить спам$"), show_spam_candidates))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^👥 Пользователи$"), admin_users_list))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📢 Рассылка$"), admin_broadcast_start))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.Regex("^◀️ Выйти$"), commands.start))

    # Callbacks
    app_bot.add_handler(CallbackQueryHandler(mark_as_spam_callback, pattern="^mark_spam_"))

    # Callbacks
    app_bot.add_handler(
        CallbackQueryHandler(admin.admin_menu_callback, pattern="^admin_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.open_web_admin, pattern="^open_web_admin$"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.admin_view_order, pattern="^admin_view_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.change_order_status, pattern="^status_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.contact_client, pattern="^contact_client_"))
    app_bot.add_handler(
        CallbackQueryHandler(callback_services, pattern="^services$"))
    app_bot.add_handler(
        CallbackQueryHandler(callback_check_status, pattern="^check_status$"))
    app_bot.add_handler(CallbackQueryHandler(callback_faq, pattern="^faq$"))
    app_bot.add_handler(
        CallbackQueryHandler(callback_contacts, pattern="^contacts$"))
    app_bot.add_handler(
        CallbackQueryHandler(callback_back, pattern="^back_menu$"))
    app_bot.add_handler(
        CallbackQueryHandler(callback_contact_master,
                             pattern="^contact_master$"))
    app_bot.add_handler(
        CallbackQueryHandler(handle_order_status_change,
                             pattern="^admin_open_"))

    # Callbacks цен
    for cat in [
            "jacket", "leather", "curtains", "coat", "fur", "outerwear",
            "pants", "dress"
    ]:
        app_bot.add_handler(
            CallbackQueryHandler(globals()[f"callback_price_{cat}"],
                                 pattern=f"^price_{cat}$"))

    # Callbacks FAQ
    for sub in [
            "services", "prices", "timing", "location", "payment", "order",
            "other"
    ]:
        app_bot.add_handler(
            CallbackQueryHandler(globals()[f"callback_faq_{sub}"],
                                 pattern=f"^faq_{sub}$"))

    app_bot.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       messages.handle_message))

    async def error_handler(update, context):
        logger.error(f"Exception: {context.error}")
        try:
            admin_id = os.getenv("ADMIN_ID")
            if admin_id:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=f"⚠️ *Ошибка:*\n`{str(context.error)[:200]}`",
                    parse_mode="Markdown")
        except:
            pass

    app_bot.add_error_handler(error_handler)
    logger.info("🤖 Бот запущен!")
    app_bot.run_polling(drop_pending_updates=True)


def run_with_restart():
    logger.info("⏳ Ожидание 5 секунд...")
    time.sleep(5)
    max_retries = 10
    retry_count = 0
    while retry_count < max_retries:
        try:
            main()
            break
        except KeyboardInterrupt:
            logger.info("Бот остановлен")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Критическая ошибка #{retry_count}: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_with_restart()
