import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
from telegram.ext import ContextTypes, ConversationHandler
from utils.database import (
    get_statistics, get_all_orders, get_all_users, get_spam_logs, 
    get_orders_by_status, update_order_status, get_order, delete_order
)
from handlers.orders import format_order_id

logger = logging.getLogger(__name__)

async def set_admin_commands(bot, user_id: int):
    commands = [
        BotCommand("start", "🏠 Админ панель"),
        BotCommand("orders", "📦 Все заказы"),
        BotCommand("stats", "📈 Статистика"),
        BotCommand("users", "👥 Пользователи"),
        BotCommand("search", "🔍 Поиск заказа"),
        BotCommand("spam", "🚫 Спам-заказы"),
        BotCommand("export", "📤 Экспорт данных"),
        BotCommand("logs", "📜 Логи действий"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeChat(user_id))

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_statistics()
    text = (
        f"📊 *Статистика за всё время*\n\n"
        f"🆕 Новых заказов: {stats.get('new_orders', 0)}\n"
        f"🔄 В работе: {stats.get('in_progress', 0)}\n"
        f"✅ Завершено: {stats.get('completed', 0)}\n"
        f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def show_spam_candidates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = get_orders_by_status("new")
    if not orders:
        await update.message.reply_text("Нет новых заказов для проверки на спам.")
        return

    for order in orders[:10]:
        formatted_id = format_order_id(order.id, order.created_at)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Пометить как спам", callback_data=f"mark_spam_{order.id}")
        ]])
        text = (
            f"📦 Заказ {formatted_id}\n"
            f"👤 От: {order.client_name}\n"
            f"📞 Тел: {order.client_phone}\n"
            f"📝 Описание: {order.description[:100] if order.description else 'Нет описания'}"
        )
        await update.message.reply_text(text, reply_markup=keyboard)

async def mark_as_spam_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.replace("mark_spam_", ""))
    
    if update_order_status(order_id, "spam"):
        await query.answer("Заказ помечен как спам")
        await query.message.edit_text(f"✅ Заказ #{order_id} помечен как спам и скрыт.")
    else:
        await query.answer("Ошибка при обновлении статуса", show_alert=True)
