"""
Обработчики callback-кнопок главного меню бота «Швейный HUB».

Модуль заменяет одноимённые «анонимные» колбэки, которые ранее были
разбросаны по main.py. Все тексты взяты из static_texts.py, данные
мастерской — из config.py (единый источник истины).

Регистрация обработчиков выполняется в register() — это устраняет
магический поиск функций через globals() в main.py.
"""

import logging
from functools import partial

from telegram import (InlineKeyboardButton,
                           InlineKeyboardMarkup, Update)
from telegram.ext import Application, CallbackQueryHandler

import static_texts as T
from keyboards import (get_back_button, get_faq_menu, get_main_menu,
                       get_prices_menu)
from utils.database import get_user_orders
from utils.prices import format_prices_text

logger = logging.getLogger(__name__)

# Категории цен и темы FAQ должны совпадать с callback_data в keyboards.py
PRICE_CATEGORIES = [
    "jacket", "leather", "curtains", "coat", "fur", "outerwear", "pants",
    "dress"
]

FAQ_TOPICS = {
    "services": T.FAQ_SERVICES_TEXT,
    "prices": T.FAQ_PRICES_TEXT,
    "timing": T.FAQ_TIMING_TEXT,
    "location": T.FAQ_LOCATION_TEXT,
    "payment": T.FAQ_PAYMENT_TEXT,
    "order": T.FAQ_ORDER_TEXT,
    "other": T.FAQ_OTHER_TEXT,
}


async def _edit(update: Update, text: str, reply_markup=None) -> None:
    """Безопасная редакция сообщения с ответом на callback-запрос."""
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(text=text,
                                      reply_markup=reply_markup,
                                      parse_mode="Markdown")
    except Exception as e:  # сообщение не изменилось / нет прав и т.п.
        logger.debug("edit_message_text failed: %s", e)


async def show_main_menu(update: Update) -> None:
    """Кнопки «◀️ Назад» / «🏠 В главное меню» — возврат в главное меню."""
    await _edit(update, T.MAIN_MENU_TITLE, get_main_menu())


async def show_services(update: Update) -> None:
    """Кнопка «📋 Услуги и цены» — выбор категории цен."""
    await _edit(update, T.SERVICES_PROMPT, get_prices_menu())


async def show_faq(update: Update) -> None:
    """Кнопка «❓ FAQ» — список тем."""
    await _edit(update, T.FAQ_PROMPT, get_faq_menu())


async def show_contacts(update: Update) -> None:
    """Кнопка «📍 Контакты»."""
    await _edit(update, T.CONTACTS_TEXT, get_back_button())


async def show_contact_master(update: Update) -> None:
    """Кнопка «👩‍🔧 Связаться с мастером»."""
    await _edit(update, T.CONTACT_MASTER_TEXT, get_back_button())


async def show_price_category(update: Update, category: str) -> None:
    """Открытие прайса по выбранной категории."""
    prices_text = format_prices_text(category)
    if prices_text:
        await _edit(update, prices_text, get_prices_menu())
    else:
        await _edit(update, T.PRICES_NOT_FOUND, get_prices_menu())


def make_faq_handler(text: str):
    """Фабрика колбэков для темы FAQ с готовым текстом ответа."""

    async def handler(update: Update) -> None:
        await _edit(update, text, get_faq_menu())

    return handler


async def check_status(update: Update) -> None:
    """Кнопка «🔍 Статус заказа» — последние 5 заказов пользователя."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    orders = get_user_orders(user_id)
    if not orders:
        text = T.NO_ORDERS_TEXT
    else:
        from handlers.orders import format_order_id
        text = T.MY_ORDERS_HEADER
        for order in orders[:5]:
            status = T.ORDER_STATUS_MAP.get(str(order.status),
                                            str(order.status))
            desc = str(order.description) if order.description else "Услуга"
            formatted_id = format_order_id(int(order.id), order.created_at)
            text += f"*{formatted_id}* - {status}\n{desc}\n\n"

    try:
        await query.edit_message_text(text=text,
                                      reply_markup=get_back_button(),
                                      parse_mode="Markdown")
    except Exception as e:
        logger.debug("edit_message_text failed: %s", e)


def register(application: Application) -> None:
    """Регистрирует все callback-обработчики главного меню.

    ИСПРАВЛЕНИЕ БАГА: раньше эти колбэки регистрировались в группе 0
    ПОСЛЕ ConversationHandler'а заказов, и PTB выбирал всегда ПЕРВЫЙ
    подходящий хендлер в группе. Пока пользователь хоть раз не «выходил»
    из диалога заказа, все кнопки меню (services/faq/contacts/категории
    цен/back_menu) перехватывались ConversationHandler'ом и молча
    игнорировались — кнопки выглядели некликабельными.

    Решение: колбэки меню вынесены в отдельную группу (group=2), которая
    обрабатывает нажатия ВСЕГДА, независимо от состояния диалога.
    Внутри группы порядок важен: сначала точные паттерны категорий,
    затем широкие service_/admin_, в конце catch-all back/menu/cancel.
    """
    from handlers import admin as admin_handlers
    from handlers.orders import select_service

    # --- Точные паттерны кнопок меню ---
    application.add_handler(
        CallbackQueryHandler(show_services, pattern="^services$"), group=2)
    application.add_handler(
        CallbackQueryHandler(check_status, pattern="^check_status$"),
        group=2)
    application.add_handler(
        CallbackQueryHandler(show_faq, pattern="^faq$"), group=2)
    application.add_handler(
        CallbackQueryHandler(show_contacts, pattern="^contacts$"), group=2)
    application.add_handler(
        CallbackQueryHandler(show_contact_master,
                             pattern="^contact_master$"), group=2)

    for cat in PRICE_CATEGORIES:
        application.add_handler(
            CallbackQueryHandler(partial(show_price_category, category=cat),
                                 pattern=f"^price_{cat}$"), group=2)

    for topic, text in FAQ_TOPICS.items():
        application.add_handler(
            CallbackQueryHandler(make_faq_handler(text),
                                 pattern=f"^faq_{topic}$"), group=2)

    # --- Широкие паттерны: категории услуг и админ-колбэки ---
    # (внутри активного диалога заказа их обработает ConversationHandler
    # в группе 0; здесь они срабатывают вне диалога)
    application.add_handler(
        CallbackQueryHandler(select_service, pattern=r"^service_"), group=2)
    # «Список отзывов» перехватывался широким паттерном ^admin_ в группе 2,
    # поэтому регистрируется РАНЬШЕ него — отдельным точным хендлером.
    async def show_review_list(update, context):
        """Кнопка «📋 Список отзывов» из статистики отзывов."""
        from utils.database import get_recent_reviews
        query = update.callback_query
        await query.answer()
        if not admin_handlers.is_user_admin(update.effective_user.id):
            await query.answer("⛔ Нет доступа", show_alert=True)
            return
        reviews = get_recent_reviews(limit=15)
        if not reviews:
            text = "📭 Отзывов пока нет."
        else:
            lines = []
            for r in reviews:
                status = "✅" if r.is_approved else ("🚫" if r.rejected_reason else "⏳")
                comment = (r.comment[:60] + "…") if r.comment and len(r.comment) > 60 else (r.comment or "—")
                lines.append(f"{status} ⭐{r.rating}: {comment}")
            text = "📋 *Последние отзывы:*\n\n" + "\n".join(lines)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📊 Статистика отзывов",
                                 callback_data="admin_review_stats")
        ], [
            InlineKeyboardButton("◀️ Назад к админ-меню",
                                 callback_data="admin_back_menu")
        ]])
        try:
            await query.edit_message_text(text, reply_markup=keyboard,
                                          parse_mode="Markdown")
        except Exception as e:
            logger.debug("show_review_list edit failed: %s", e)

    application.add_handler(
        CallbackQueryHandler(show_review_list,
                             pattern=r"^admin_review_list$"), group=2)

    application.add_handler(
        CallbackQueryHandler(admin_handlers.admin_menu_callback,
                             pattern=r"^admin_"), group=2)
    application.add_handler(
        CallbackQueryHandler(admin_handlers.change_order_status,
                             pattern=r"^status_"), group=2)
    application.add_handler(
        CallbackQueryHandler(admin_handlers.contact_client,
                             pattern=r"^contact_client_"), group=2)

    # --- Catch-all: возврат в главное меню / отмена ---
    # Охватывает back_menu, menu (кнопки из отзывов) и cancel_order.
    # Регистрируется ПОСЛЕДНИМ, чтобы точные паттерны выше имели приоритет.
    application.add_handler(
        CallbackQueryHandler(show_main_menu,
                             pattern=r"^(back_menu|menu|cancel_order)$"),
        group=2)

    # --- Админ-колбэки, дублированные вне группы 0 ---
    # admin_view_<id>: если у админа «завис» активный диалог заказа/отзыва
    # (группа 0), кнопки списка заказов иначе молча игнорировались.
    application.add_handler(
        CallbackQueryHandler(admin_handlers.admin_menu_callback,
                             pattern=r"^admin_view_\d+$"), group=3)

    # --- Колбэки отзывов ---
    # В группе 0 зарегистрирован только ConversationHandler отзыва
    # (entry review_rate:...). Остальные кнопки уведомлений об отзывах
    # нигде не были подключены — get_admin_review() возвращает их хендлеры,
    # которые раньше никто не вызывал («мёртвые» некликабельные кнопки).
    from handlers.reviews import get_admin_review_handlers

    for handler in get_admin_review_handlers():
        application.add_handler(handler, group=4)


