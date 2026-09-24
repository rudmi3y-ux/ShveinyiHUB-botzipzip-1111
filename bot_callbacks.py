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

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler

import static_texts as T
from keyboards import get_back_button, get_faq_menu, get_main_menu, get_prices_menu
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
    """Кнопка «◀️ Назад» — возврат в главное меню."""
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
    """Регистрирует все callback-обработчики главного меню."""
    application.add_handler(
        CallbackQueryHandler(show_services, pattern="^services$"))
    application.add_handler(
        CallbackQueryHandler(check_status, pattern="^check_status$"))
    application.add_handler(CallbackQueryHandler(show_faq, pattern="^faq$"))
    application.add_handler(
        CallbackQueryHandler(show_contacts, pattern="^contacts$"))
    application.add_handler(
        CallbackQueryHandler(show_main_menu, pattern="^back_menu$"))
    application.add_handler(
        CallbackQueryHandler(show_contact_master,
                             pattern="^contact_master$"))

    for cat in PRICE_CATEGORIES:
        application.add_handler(
            CallbackQueryHandler(partial(show_price_category, category=cat),
                                 pattern=f"^price_{cat}$"))

    for topic, text in FAQ_TOPICS.items():
        application.add_handler(
            CallbackQueryHandler(make_faq_handler(text),
                                 pattern=f"^faq_{topic}$"))
