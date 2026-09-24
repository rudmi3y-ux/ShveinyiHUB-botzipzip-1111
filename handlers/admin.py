"""
Полнофункциональный обработчик админ-панели для бота.

Реализовано:
- команды: /admin, /stats, /orders, /neworders, /users, /spam, /broadcast, /setadmin
- callback-обработчики админ-меню: admin_menu_callback, admin_view_order,
  change_order_status, contact_client, open_web_admin
- интеграция с utils.database и keyboards
- безопасные проверки прав (ENV ADMIN_ID + флаг is_admin из БД)
"""
import os
import logging
import asyncio
from typing import List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Локальные зависимости (должны существовать в проекте)
from utils.database import (
    get_statistics,
    get_all_orders,
    get_all_users,
    get_spam_logs,
    set_admin,
    is_admin,
    get_orders_by_status,
    get_order,
    update_order_status,
    get_admins,
)
from keyboards import (
    get_admin_main_menu,
    get_admin_orders_submenu,
    get_admin_back_menu,
    get_admin_order_detail_keyboard,
)

logger = logging.getLogger(__name__)

# Конфигурация
try:
    ENV_ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else 0
except Exception:
    ENV_ADMIN_ID = 0

WEB_ADMIN_URL = os.getenv("WEB_ADMIN_URL") or f"https://{os.getenv('REPLIT_DEV_DOMAIN')}" or ""


def _get_web_admin_orders_url() -> str:
    """Сформировать URL веб-админки для страницы заказов"""
    if WEB_ADMIN_URL:
        # Убираем /admin/orders и оставляем просто /orders, так как в app.py роут /orders
        return f"{WEB_ADMIN_URL.rstrip('/')}/orders"
    return ""


def get_admin_ids() -> List[int]:
    """Вернуть список admin ids (ENV + БД)"""
    ids = []
    if ENV_ADMIN_ID:
        ids.append(int(ENV_ADMIN_ID))
    try:
        db_admins = get_admins() if callable(get_admins) else []
        for a in db_admins:
            try:
                ids.append(int(a.user_id))
            except Exception:
                pass
    except Exception:
        logger.debug("get_admins not available or failed")
    return ids


def is_user_admin(user_id: int) -> bool:
    """Проверка прав администратора: ENV_ADMIN_ID или is_admin из БД"""
    if not user_id:
        return False
    try:
        if ENV_ADMIN_ID and int(user_id) == int(ENV_ADMIN_ID):
            return True
    except (ValueError, TypeError):
        pass
    try:
        return bool(is_admin(user_id))
    except Exception:
        return False


# ---------------- Команды ----------------


async def admin_panel_command(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin — показать главное админ-меню"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    try:
        stats = get_statistics()
    except Exception:
        stats = {}
    text = "📋 *Админ-панель*\n\nВыберите раздел для управления:"
    await update.effective_message.reply_text(
        text, reply_markup=get_admin_main_menu(), parse_mode="Markdown")


async def admin_stats(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats — показать статистику"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.effective_message.reply_text("⛔ У вас нет доступа.")
        return

    try:
        from utils.database import get_statistics
        stats = get_statistics()
        text = ("📊 *Статистика бота*\n\n"
                f"👥 Пользователей: {stats.get('total_users', 0)}\n"
                f"📦 Всего заказов: {stats.get('total_orders', 0)}\n"
                f"🆕 Новых: {stats.get('new_orders', 0)}\n"
                f"🔄 В работе: {stats.get('in_progress', 0)}\n"
                f"✅ Выполнено: {stats.get('completed', 0)}\n"
                f"📤 Выдано: {stats.get('issued', 0)}\n"
                f"🚫 Заблокировано: {stats.get('blocked_users', 0)}\n"
                f"🛑 Спам-записей: {stats.get('spam_count', 0)}")
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats"),
            InlineKeyboardButton("◀️ Назад", callback_data="admin_back_menu")
        ]])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при формировании статистики")
        error_text = "❌ Ошибка при получении статистики."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.effective_message.reply_text(error_text)


async def admin_orders(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """/orders — вывести последние заказы с кнопками управления"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.effective_message.reply_text("⛔ У вас нет доступа.")
        return

    try:
        orders = get_all_orders(limit=20)
        if not orders:
            await update.effective_message.reply_text("📋 Заказов пока нет.")
            return

        from handlers.orders import format_order_id
        text = "📋 *Последние заказы:*\n\nВыберите заказ для управления:"
        keyboard = []
        for order in orders:
            formatted = format_order_id(int(order.id), order.created_at)
            status_emoji = {
                "new": "🆕",
                "in_progress": "🔄",
                "completed": "✅",
                "cancelled": "❌",
                "issued": "📤",
                "spam": "🚫",
            }.get(str(order.status), "❓")
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_emoji} {formatted} — {order.client_name or 'Аноним'}",
                    callback_data=f"admin_view_{order.id}"
                )
            ])
            
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при получении заказов")
        await update.effective_message.reply_text("❌ Не удалось получить заказы.")


async def admin_new_orders(update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    """/neworders — показать новые заказы"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    try:
        orders = get_orders_by_status("new")
        if not orders:
            await update.message.reply_text("✅ Новых заказов нет.")
            return
        from handlers.orders import format_order_id
        text = f"🆕 *Новые заказы ({len(orders)}):*\n\n"
        for order in orders[:20]:
            formatted = format_order_id(order.id, order.created_at)
            text += f"*{formatted}* — {order.client_name or '—'} | 📞 {order.client_phone or '—'}\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при получении новых заказов")
        await update.message.reply_text("❌ Ошибка при получении новых заказов."
                                        )


async def admin_users(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    """/users — список пользователей"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    try:
        users = get_all_users()
        if not users:
            if update.callback_query:
                await update.callback_query.edit_message_text("👥 Пользователей нет.")
            else:
                await update.message.reply_text("👥 Пользователей нет.")
            return
        text = f"👥 *Пользователи ({len(users)}):*\n\n"
        for u in users[:50]:
            name = u.first_name or u.username or f"ID: {u.user_id}"
            line = f"• {name}"
            if u.phone:
                line += f" ({u.phone})"
            text += line + "\n"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при получении пользователей")
        error_text = "❌ Ошибка при получении пользователей."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)


async def admin_spam(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> None:
    """/spam — показать журнал спама"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    try:
        logs = get_spam_logs(limit=50)
        if not logs:
            await update.message.reply_text("🛑 Записей спама нет.")
            return
        text = "🛑 *Последние спам-записи:*\n\n"
        for l in logs[:50]:
            text += f"👤 {l.user_id} • {l.reason}\n{(l.message[:120] + '...') if l.message else ''}\n\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при получении spam logs")
        await update.message.reply_text("❌ Ошибка при получении журнала спама."
                                        )


# ---------------- Рассылка ----------------


async def broadcast_start(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запустить режим рассылки (следующий текст — рассылка)"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    context.user_data["broadcast_mode"] = True
    await update.message.reply_text(
        "📣 Режим рассылки включён. Введите текст сообщения для рассылки. /cancel — отменить."
    )


async def broadcast_send(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить рассылку всем пользователям"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        return

    if context.args:
        message_text = " ".join(context.args)
    elif update.message and update.message.text:
        message_text = update.message.text
    else:
        await update.message.reply_text("❌ Нет текста для рассылки.")
        return

    if message_text == "/cancel":
        context.user_data["broadcast_mode"] = False
        await update.message.reply_text("❌ Рассылка отменена.")
        return

    try:
        users = get_all_users()
    except Exception:
        logger.exception("Ошибка при получении списка пользователей")
        await update.message.reply_text(
            "❌ Не удалось получить список пользователей.")
        return

    sent = 0
    failed = 0
    delay = float(os.getenv("BROADCAST_DELAY", "0.05"))

    status_msg = await update.message.reply_text(
        f"📤 Запускаю рассылку {len(users)} пользователям...")
    
    for u in users:
        try:
            await context.bot.send_message(chat_id=int(u.user_id),
                                           text=message_text,
                                           parse_mode="Markdown")
            sent += 1
            if delay:
                await asyncio.sleep(delay)
            
            if sent % 10 == 0:
                try:
                    await status_msg.edit_text(f"📤 Отправлено: {sent} / {len(users)}...")
                except: pass
        except Exception:
            failed += 1
            # logger.warning(f"Не удалось отправить пользователю {u.user_id}")
            
    await update.message.reply_text(
        f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}.")


# ---------------- Управление правами ----------------


async def set_admin_command(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> None:
    """/setadmin <user_id> — назначить пользователя админом"""
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /setadmin <user_id>")
        return

    try:
        new_admin_id = int(context.args[0])
        ok = set_admin(new_admin_id, True)
        if ok:
            await update.message.reply_text(
                f"✅ Пользователь {new_admin_id} назначен админом.")
        else:
            await update.message.reply_text(
                "❌ Не удалось назначить администратора.")
    except Exception:
        logger.exception("Ошибка в set_admin_command")
        await update.message.reply_text(
            "❌ Ошибка при назначении администратора.")


# ---------------- Callback-обработчики ----------------


async def admin_menu_callback(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка callback'ов из админ-меню"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    data = query.data or ""

    # Кнопки детального просмотра заказа: admin_view_<id>.
    # (В группе 0 этот колбэк может быть перехвачен ConversationHandler'ом,
    # поэтому обрабатываем его и здесь.)
    if data.startswith("admin_view_"):
        await admin_view_order(update, context)
        return

    # Обработка команд из Reply Keyboard
    if data == "📊 Все заказы":
        await admin_orders(update, context)
        return

    if data == "📢 Рассылка":
        await broadcast_start(update, context)
        return
    
    if data == "admin_orders_menu":
        await query.edit_message_text(
            "📦 *Управление заказами*\n\nВыберите категорию заказов:",
            reply_markup=get_admin_orders_submenu(),
            parse_mode="Markdown")
        return

    if data == "admin_back_menu":
        await query.edit_message_text(
            "📋 *Админ-панель*\n\nВыберите раздел для управления:",
            reply_markup=get_admin_main_menu(),
            parse_mode="Markdown")
        return

    if data == "admin_stats":
        await admin_stats(update, context)
        return

    if data == "admin_clients":
        await admin_users(update, context)
        return

    if data == "open_web_admin":
        url = _get_web_admin_orders_url() or "Веб-панель недоступна"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Открыть веб-админку", url=url)
        ], [InlineKeyboardButton("◀️ Назад",
                                 callback_data="admin_back_menu")]])
        await query.edit_message_text(f"🌐 Веб-панель: {url}",
                                      reply_markup=keyboard,
                                      parse_mode="Markdown")
        return

    status_map = {
        "admin_orders_new": ("new", "🆕 Новые заказы"),
        "admin_orders_in_progress": ("in_progress", "🔄 Заказы в работе"),
        "admin_orders_completed": ("completed", "✅ Готовые заказы"),
        "admin_orders_issued": ("issued", "📤 Выданные заказы"),
    }
    if data in status_map:
        status, title = status_map[data]
        try:
            orders = get_orders_by_status(status)
            if not orders:
                await query.edit_message_text(
                    f"{title}\n\n📭 Заказов нет",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀️ Назад",
                                             callback_data="admin_back_menu")
                    ]]),
                    parse_mode="Markdown")
                return
            from handlers.orders import format_order_id
            text = f"*{title}* ({len(orders)}):\n\n"
            keyboard = []
            for order in orders[:20]:
                formatted = format_order_id(int(order.id), order.created_at)
                phone = order.client_phone or "📲 TG"
                text += f"📦 {formatted} — {order.client_name or 'Аноним'} | {phone}\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"📦 {formatted}",
                        callback_data=f"admin_view_{order.id}")
                ])
            keyboard.append([
                InlineKeyboardButton("◀️ Назад",
                                     callback_data="admin_back_menu")
            ])
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown")
        except Exception:
            logger.exception("Ошибка получения заказов по статусу")
            await query.edit_message_text(
                "❌ Ошибка при получении заказов.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад",
                                         callback_data="admin_back_menu")
                ]]))
        return

    if data.startswith("admin_view_"):
        await admin_view_order(update, context)
        return

    # Прочие колбэки (в т.ч. чужие пространства имён, например admin_review_*),
    # которые здесь не обрабатываются, молча пропускаем — их подхватят
    # собственные хендлеры в других группах.
    if not data.startswith(("status_", "contact_client_")):
        logger.debug("admin_menu_callback: необрабатываемый колбэк %s", data)
        return

    if data.startswith("status_") and not data.startswith("status_deleted_"):
        await change_order_status(update, context)
        return

    if data.startswith("contact_client_"):
        await contact_client(update, context)
        return

    if data.startswith("status_deleted_"):
        try:
            order_id = int(data.replace("status_deleted_", ""))
            from utils.database import delete_order
            if delete_order(order_id):
                await query.answer("✅ Заказ удален")
                await query.message.edit_text(f"🗑 Заказ #{order_id} был удален из базы данных.")
            else:
                await query.answer("❌ Ошибка при удалении", show_alert=True)
        except Exception as e:
            logger.error(f"Error deleting order: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
        return

    await query.answer("Неизвестное действие.", show_alert=True)


async def admin_view_order(update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    """Просмотр заказа с кнопками управления"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        order_id = int(query.data.replace("admin_view_", ""))
    except Exception:
        await query.answer("❌ Неверный ID заказа", show_alert=True)
        return

    order = get_order(order_id)
    if not order:
        await query.answer("❌ Заказ не найден", show_alert=True)
        return

    from handlers.orders import format_order_id, WORKSHOP_ADDRESS, WORKSHOP_PHONE
    formatted = format_order_id(order.id, order.created_at)
    status_emoji = {
        "new": "🆕",
        "in_progress": "🔄",
        "completed": "✅",
        "cancelled": "❌",
        "issued": "📤",
        "spam": "🚫",
    }.get(str(order.status), "❓")
    
    status_text_display = {
        "new": "Новый",
        "in_progress": "В работе",
        "completed": "Готов",
        "issued": "Выдан",
        "cancelled": "Отменён",
        "spam": "Спам"
    }.get(str(order.status), str(order.status))

    # Кнопки детального управления (В работу, Выполнен, Удалить)
    keyboard = get_admin_order_detail_keyboard(order.id, order.status)
    
    text = (
        f"📦 *Заказ {formatted}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 *Статус:* {status_emoji} {status_text_display}\n"
        f"🏷 *Услуга:* {order.service_type or '—'}\n"
        f"👤 *Клиент:* {order.client_name or 'Аноним'}\n"
        f"📞 *Телефон:* {order.client_phone or '—'}\n"
        f"📝 *Описание:* {order.description or 'Нет описания'}\n"
        f"📅 *Дата:* {order.created_at.strftime('%d.%m.%Y %H:%M') if order.created_at else 'Н/Д'}\n"
    )
    try:
        if getattr(query.message, "photo", None) or order.photo_file_id:
            try:
                await query.message.delete()
            except Exception:
                pass
            if order.photo_file_id:
                await context.bot.send_photo(chat_id=query.message.chat_id,
                                             photo=order.photo_file_id,
                                             caption=text,
                                             reply_markup=keyboard,
                                             parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=query.message.chat_id,
                                               text=text,
                                               reply_markup=keyboard,
                                               parse_mode="Markdown")
        else:
            await query.edit_message_text(text,
                                          reply_markup=keyboard,
                                          parse_mode="Markdown")
    except Exception:
        logger.exception("Ошибка при отображении заказа админом")
        await query.edit_message_text(text,
                                      reply_markup=keyboard,
                                      parse_mode="Markdown")


async def change_order_status(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """Изменение статуса заказа админом"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_user_admin(user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    data = query.data or ""
    parts = data.split("_")
    if len(parts) < 3:
        await query.answer("❌ Неверный формат данных", show_alert=True)
        return

    try:
        new_status = parts[1] if parts[0] == "status" else parts[1]
        order_id = int(parts[-1])
    except Exception:
        await query.answer("❌ Неверный ID заказа", show_alert=True)
        return

    mapping = {
        "in": "in_progress",
        "inprogress": "in_progress",
        "in_progress": "in_progress",
        "completed": "completed",
        "issued": "issued",
        "cancelled": "cancelled",
        "cancel": "cancelled",
    }
    new_status_norm = mapping.get(new_status, new_status)

    try:
        updated = update_order_status(order_id, new_status_norm)
    except Exception:
        logger.exception("Ошибка при обновлении статуса заказа в БД")
        await query.answer("❌ Ошибка при обновлении статуса", show_alert=True)
        return

    if not updated:
        await query.answer("❌ Заказ не найден или не обновлён",
                           show_alert=True)
        return

    order = get_order(order_id)
    try:
        from handlers.orders import format_order_id
        formatted = format_order_id(
            order.id, order.created_at) if order else f"#{order_id}"
        client_msgs = {
            "in_progress": f"✂️ Ваша вещь в работе.\nЗаказ: {formatted}",
            "completed":
            f"🎉 Заказ готов!\nЗаказ: {formatted}\nПриходите за выдачей.",
            "issued": f"📤 Заказ выдан.\nЗаказ: {formatted}",
            "cancelled": f"❌ Заказ отменён.\nЗаказ: {formatted}",
            "new": f"🆕 Ваш заказ зарегистрирован: {formatted}"
        }
        client_text = client_msgs.get(
            new_status_norm, f"📦 Статус заказа обновлён: {new_status_norm}")
        if order and getattr(order, "user_id", None):
            try:
                await context.bot.send_message(chat_id=order.user_id,
                                               text=client_text)
            except Exception:
                logger.warning(
                    f"Не удалось уведомить пользователя {order.user_id}")
    except Exception:
        logger.exception(
            "Ошибка при уведомлении клиента после изменения статуса")

    try:
        status_text_map = {
            "in_progress": "🔄 В работе",
            "completed": "✅ Готов",
            "issued": "📤 Выдан",
            "cancelled": "❌ Отменён",
            "new": "🆕 Новый"
        }
        status_text = status_text_map.get(new_status_norm, new_status_norm)
        admin_name = user.username or user.first_name or str(user.id)
        formatted_id = f"#{order_id}"
        try:
            from handlers.orders import format_order_id
            if order:
                formatted_id = format_order_id(order.id, order.created_at)
        except Exception:
            pass
        new_text = f"✅ Заказ {formatted_id} обновлён\n\n{status_text}\n\n👤 Обновил: @{admin_name}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ К списку заказов",
                                 callback_data="admin_orders_menu")
        ]])
        if query.message and getattr(query.message, "photo", None):
            try:
                await query.message.edit_caption(caption=new_text,
                                                 reply_markup=keyboard)
            except Exception:
                await query.edit_message_text(text=new_text,
                                              reply_markup=keyboard)
        else:
            await query.edit_message_text(text=new_text, reply_markup=keyboard)
    except Exception:
        logger.exception(
            "Ошибка при обновлении сообщения админа после смены статуса")


async def contact_client(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать способы связи с клиентом"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        order_id = int(query.data.replace("contact_client_", ""))
    except Exception:
        await query.answer("❌ Неверный ID заказа", show_alert=True)
        return

    order = get_order(order_id)
    if not order:
        await query.answer("❌ Заказ не найден", show_alert=True)
        return

    phone = order.client_phone or "Не указан"
    tg_url = f"tg://user?id={order.user_id}" if order.user_id else None
    buttons = []
    if tg_url:
        buttons.append(
            [InlineKeyboardButton("✉️ Написать в Telegram", url=tg_url)])
    buttons.append([
        InlineKeyboardButton("◀️ Назад",
                             callback_data=f"admin_view_{order_id}")
    ])
    await query.edit_message_text(
        f"✉️ *Связь с клиентом*\n\n👤 {order.client_name or 'Не указано'}\n📞 {phone}\n\nНажмите кнопку для связи.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons))


async def open_web_admin(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """Открытие веб-админки"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    url = _get_web_admin_orders_url()
    if not url:
        await query.answer("❌ Веб-панель не настроена", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Открыть веб-админку", url=url)],
         [InlineKeyboardButton("◀️ Назад", callback_data="admin_back_menu")]])
    await query.edit_message_text(f"🌐 *Веб-панель администратора*\n\n{url}",
                                  reply_markup=keyboard,
                                  parse_mode="Markdown")


# ---------------- Вспомогательные функции ----------------


def get_admin_menu_keyboard(
        stats: Optional[dict] = None) -> InlineKeyboardMarkup:
    """Клавиатура админ-меню (с метриками)"""
    if stats is None:
        try:
            stats = get_statistics()
        except Exception:
            stats = {}
    new_count = stats.get("new_orders", 0)
    in_progress = stats.get("in_progress", 0)
    completed = stats.get("completed", 0)
    issued = stats.get("issued", 0)
    keyboard = [
        [
            InlineKeyboardButton(f"🆕 Новые ({new_count})",
                                 callback_data="admin_orders_new"),
            InlineKeyboardButton(f"🔄 В работе ({in_progress})",
                                 callback_data="admin_orders_in_progress")
        ],
        [
            InlineKeyboardButton(f"✅ Готовые ({completed})",
                                 callback_data="admin_orders_completed"),
            InlineKeyboardButton(f"📤 Выданные ({issued})",
                                 callback_data="admin_orders_issued")
        ],
        [
            InlineKeyboardButton("👥 Клиенты", callback_data="admin_clients"),
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("🌐 Веб-админка",
                                 callback_data="open_web_admin"),
            InlineKeyboardButton("◀️ Назад", callback_data="admin_back_menu")
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
