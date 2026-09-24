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
from webapp.app import app

from telegram import Update, MenuButtonCommands, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          CallbackQueryHandler, MessageHandler,
                          ConversationHandler, filters, TypeHandler, ContextTypes)

import static_texts as T
from config import (ADMIN_ID, BOT_TOKEN, DISABLE_INSTANCE_LOCK, FLASK_PORT,
                    LOCK_PORT)
from handlers import commands, messages, admin
from handlers.commands import faq_command, status_command

# --- ИМПОРТЫ ЗАКАЗОВ ---
from handlers.orders import (
    order_start, select_service, receive_photo, skip_photo, enter_name,
    enter_phone, confirm_order, cancel_order, use_tg_name, skip_phone as
    skip_phone_handler, handle_order_status_change, enter_description,
    skip_description, ENTER_DESCRIPTION, SELECT_SERVICE, SEND_PHOTO,
    ENTER_NAME, ENTER_PHONE, CONFIRM_ORDER, get_order_conversation_handler)
# ----------------------------

from handlers.reviews import get_review_conversation_handler, request_review
from keyboards import get_main_menu, get_prices_menu, get_admin_main_menu
from utils.database import (init_db, get_orders_pending_feedback,
                            mark_feedback_requested)
from utils.prices import import_prices_data
import bot_callbacks

_lock = None
logger = logging.getLogger(__name__)


# --- БЛОКИРОВКА ПОВТОРНОГО ЗАПУСКА ---
def create_lock():
    """Запрещает запуск второго экземпляра бота (сокет-локальный замок)."""
    global _lock
    if DISABLE_INSTANCE_LOCK:
        return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        s.setblocking(False)
        _lock = {"type": "socket", "obj": s, "port": LOCK_PORT}
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

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
BOT_START_TIME = time.time()

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)


# Команды меню
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.jpg")


async def show_menu_with_logo(message, name):
    caption = T.MENU_WITH_LOGO_CAPTION.format(name=name)
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as photo:
            await message.reply_photo(photo=photo,
                                      caption=caption,
                                      parse_mode="Markdown")
    else:
        await message.reply_text(caption, parse_mode="Markdown")
    await message.reply_text(T.MAIN_MENU_TITLE,
                             reply_markup=get_main_menu(),
                             parse_mode="Markdown")


async def services_command(update, context):
    if update.message:
        await update.message.reply_text(text=T.SERVICES_PROMPT,
                                        reply_markup=get_prices_menu())


async def contact_command(update, context):
    if update.message:
        await update.message.reply_text(T.CONTACT_COMMAND_TEXT,
                                        parse_mode="Markdown")


async def menu_command(update, context):
    user = update.effective_user
    name = user.first_name or "друг"
    message = update.message or (update.callback_query.message
                                 if update.callback_query else None)
    if message:
        await show_menu_with_logo(message, name)


async def admin_panel_command(update, context):
    from handlers.admin import is_user_admin
    if not is_user_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text(T.NO_ADMIN_ACCESS)
        return
    if update.message:
        await update.message.reply_text(T.ADMIN_PANEL_TITLE,
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


def _run_flask() -> None:
    """Запуск веб-админки Flask в отдельном потоке.

    В Replit 5000 — стандартный порт для webview, поэтому по умолчанию
    используется альтернативный порт (см. config.FLASK_PORT).
    """
    try:
        app.run(host="0.0.0.0", port=FLASK_PORT, use_reloader=False,
                threaded=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске Flask: {e}")


# --- ГЛАВНАЯ ФУНКЦИЯ ---
def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return

    threading.Thread(target=_run_flask, daemon=True).start()
    time.sleep(3)  # даём Flask время на запуск

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

    # Broadcast message handler
    async def handle_broadcast_message(update: Update,
                                       context: ContextTypes.DEFAULT_TYPE):
        from handlers.admin import is_user_admin, broadcast_send
        if not update.effective_user or not is_user_admin(
                update.effective_user.id):
            return

        if context.user_data.get("broadcast_mode"):
            if update.message and update.message.text:
                if update.message.text == "/cancel":
                    context.user_data["broadcast_mode"] = False
                    await update.message.reply_text(T.BROADCAST_CANCELLED)
                    return

                await broadcast_send(update, context)
                context.user_data["broadcast_mode"] = False

    app_bot.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_broadcast_message), group=1)

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

    # Админ-команды и текстовые кнопки админа
    from handlers.admin import (admin_orders as admin_orders_list,
                                admin_stats as admin_stats_info,
                                admin_users as admin_users_list,
                                admin_spam as admin_spam_logs,
                                broadcast_start as admin_broadcast_start)
    from handlers.admin_panel.handlers import (show_spam_candidates,
                                               mark_as_spam_callback)

    app_bot.add_handler(CommandHandler("admin", admin_panel_command))
    app_bot.add_handler(CommandHandler("stats", admin_stats_info))
    app_bot.add_handler(CommandHandler("orders", admin_orders_list))
    app_bot.add_handler(CommandHandler("users", admin_users_list))
    app_bot.add_handler(CommandHandler("spam", admin_spam_logs))
    app_bot.add_handler(CommandHandler("broadcast", admin_broadcast_start))
    app_bot.add_handler(
        CommandHandler("search", admin_orders_list))  # Позже добавим поиск

    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^📈 Статистика$"),
                       admin_stats_info))
    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^📊 Все заказы$"),
                       admin_orders_list))
    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^❌ Удалить спам$"),
                       show_spam_candidates))
    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^👥 Пользователи$"),
                       admin_users_list))
    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^📢 Рассылка$"),
                       admin_broadcast_start))
    app_bot.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^◀️ Выйти$"),
                       commands.start))

    # Callbacks админ-панели
    app_bot.add_handler(
        CallbackQueryHandler(mark_as_spam_callback, pattern="^mark_spam_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.admin_menu_callback, pattern="^admin_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.open_web_admin, pattern="^open_web_admin$"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.admin_view_order, pattern="^admin_view_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.change_order_status, pattern="^status_"))
    app_bot.add_handler(
        CallbackQueryHandler(admin.contact_client,
                             pattern="^contact_client_"))
    app_bot.add_handler(
        CallbackQueryHandler(handle_order_status_change,
                             pattern="^admin_open_"))

    # Callbacks главного меню (услуги/цены, статус, FAQ, контакты)
    bot_callbacks.register(app_bot)

    app_bot.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       messages.handle_message))

    async def error_handler(update, context):
        logger.error(f"Exception: {context.error}")
        try:
            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=int(ADMIN_ID),
                    text=f"⚠️ *Ошибка:*\\n`{str(context.error)[:200]}`",
                    parse_mode="Markdown")
        except Exception:
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
