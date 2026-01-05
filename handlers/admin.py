import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

# Настройка логирования
logger = logging.getLogger(__name__)

# ID администратора из переменных окружения с обработкой ошибок
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    if ADMIN_ID == 0:
        logger.warning(
            "ADMIN_ID не установлен или равен 0. Админ-функции будут недоступны."
        )
except (ValueError, TypeError) as e:
    ADMIN_ID = 0
    logger.error(f"Ошибка при чтении ADMIN_ID: {e}. Установлено значение 0.")


def is_user_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id == ADMIN_ID and ADMIN_ID != 0


def get_admin_stats() -> dict:
    """Получение статистики для администратора"""
    # Здесь можно добавить реальную статистику из базы данных
    stats = {
        "users": 0,
        "orders": 0,
        "messages": 0,
        "reviews": 0,
        "active_commands": 0,
        "active_sessions": 0
    }
    return stats


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики администратора"""
    if not is_user_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    try:
        stats = get_admin_stats()
        message = ("📊 **Статистика бота:**\n\n"
                   f"👥 Пользователей: {stats['users']}\n"
                   f"📦 Заказов: {stats['orders']}\n"
                   f"💬 Сообщений: {stats['messages']}\n"
                   f"⭐ Отзывов: {stats['reviews']}\n"
                   f"⚡ Активных команд: {stats['active_commands']}\n"
                   f"🔄 Активных сессий: {stats['active_sessions']}")
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при получении статистики.")


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь по административным командам"""
    if not is_user_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    help_text = ("🛠 **Доступные административные команды:**\n\n"
                 "/admin_stats - Показать статистику бота\n"
                 "/admin_users - Управление пользователями\n"
                 "/admin_orders - Управление заказами\n"
                 "/admin_reviews - Управление отзывами\n"
                 "/admin_broadcast - Рассылка сообщений пользователям\n"
                 "/request_review - Запросить отзыв у пользователя\n\n"
                 "📱 *Быстрые действия через меню:*\n"
                 "• Просмотр новых заказов\n"
                 "• Изменение статусов заказов\n"
                 "• Модерация отзывов\n"
                 "• Отправка уведомлений")
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка сообщений всем пользователям"""
    if not is_user_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    if not context.args:
        await update.message.reply_text(
            "✉️ **Использование:** /admin_broadcast <текст сообщения>\n\n"
            "**Пример:** /admin_broadcast Привет всем пользователям!\n\n"
            "⚠️ *Внимание:* Сообщение будет отправлено всем пользователям бота.",
            parse_mode="Markdown")
        return

    broadcast_message = " ".join(context.args)

    # Здесь будет логика рассылки пользователям
    # Нужно получить список всех пользователей из БД

    await update.message.reply_text(
        f"📢 **Сообщение для рассылки:**\n\n{broadcast_message}\n\n"
        f"❕ Функция рассылки находится в разработке.\n"
        f"*В будущем здесь будет:*\n"
        f"• Подтверждение перед отправкой\n"
        f"• Прогресс отправки\n"
        f"• Отчет о доставке",
        parse_mode="Markdown")


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление пользователями"""
    if not is_user_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    # Заглушка для управления пользователями
    await update.message.reply_text(
        "👥 **Управление пользователями**\n\n"
        "В разработке:\n"
        "• Просмотр списка пользователей\n"
        "• Поиск пользователей\n"
        "• Статистика активности\n"
        "• Блокировка/разблокировка\n\n"
        "Пока используйте веб-панель для управления пользователями.",
        parse_mode="Markdown")


async def broadcast_send(update: Update,
                         context: ContextTypes.DEFAULT_TYPE,
                         message_text: str = None):
    """Отправка рассылки (вызывается из режима рассылки)"""
    try:
        if not is_user_admin(update.effective_user.id):
            return

        if not message_text:
            if update.message and update.message.text:
                message_text = update.message.text
            else:
                await update.message.reply_text("❌ Нет текста для рассылки.")
                return

        # Сбрасываем режим рассылки
        if 'broadcast_mode' in context.user_data:
            context.user_data.pop('broadcast_mode')

        # Здесь будет реальная отправка всем пользователям
        # Пока просто уведомляем администратора
        await update.message.reply_text(
            f"✅ **Готово к рассылке:**\n\n{message_text}\n\n"
            f"*В разработке:*\n"
            f"В будущем здесь будет отправка {0} пользователям.",
            parse_mode="Markdown")

        logger.info(
            f"Администратор {update.effective_user.id} подготовил рассылку: {message_text[:50]}..."
        )

    except Exception as e:
        logger.error(f"Ошибка в broadcast_send: {e}")
        await update.message.reply_text("❌ Ошибка при подготовке рассылки.")


# Функция для получения списка администраторов (может быть использована в других модулях)
def get_admin_list() -> list:
    """Получить список ID администраторов"""
    admins = [ADMIN_ID] if ADMIN_ID != 0 else []

    # Здесь можно добавить получение дополнительных администраторов из БД
    # Например: from utils.database import get_admins

    return admins


# Проверка прав администратора (декоратор для функций)
def admin_required(func):
    """Декоратор для проверки прав администратора"""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      *args, **kwargs):
        if not is_user_admin(update.effective_user.id):
            if update.callback_query:
                await update.callback_query.answer(
                    "❌ У вас нет прав администратора.", show_alert=True)
            else:
                await update.message.reply_text(
                    "❌ У вас нет прав администратора.")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin orders handler"""
    await update.message.reply_text("📦 Заказы")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin stats handler"""
    await update.message.reply_text("📊 Статистика")

    async def admin_new_orders(update: Update,
                               context: ContextTypes.DEFAULT_TYPE):
        """Admin new orders handler"""
        await update.message.reply_text("📦 Новые заказы")


# Force reload
