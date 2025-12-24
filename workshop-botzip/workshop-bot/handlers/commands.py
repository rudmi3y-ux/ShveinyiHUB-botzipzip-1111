import os
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu, get_admin_main_menu, remove_keyboard
from utils.database import add_user, check_today_first_visit

WORKSHOP_ADDRESS = "г.Москва ул.Маршала Федоренко д.12, 1 этаж"
WORKSHOP_PHONE = "+7 (968) 396-91-52"
HOURS = "Пн-Чт: 10:00-19:50, Пт: 10:00-19:00, Сб: 10:00-17:00, Вс: выходной"
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.jpg")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start с умным приветствием и заставкой"""
    user = update.effective_user
    name = user.first_name or "друг"
    
    add_user(user.id, user.username, user.first_name, user.last_name)
    today_first_visit = check_today_first_visit(user.id)
    
    from handlers.admin import is_user_admin
    user_is_admin = is_user_admin(user.id)
    
    if user_is_admin:
        caption = (
            f"🛠 *Панель администратора*\n\n"
            f"Добро пожаловать, {name}!\n"
            f"Выберите раздел для управления:"
        )
        
        temp_msg = await update.message.reply_text("🪡", reply_markup=remove_keyboard())
        await temp_msg.delete()
        
        await update.message.reply_text(
            caption,
            reply_markup=get_admin_main_menu(),
            parse_mode="Markdown"
        )
        return
    
    if today_first_visit:
        caption = (
            f"✨ _*весело подпрыгивая*_ ✨\n\n"
            f"Привет-привет, {name}! Я — *Иголочка*, помощница «Швейного HUBа»! 🪡\n\n"
            f"Готова пронзить любую вашу швейную проблему своей экспертизой!\n"
            f"Расскажите — сострочим решение вместе, или воспользуйтесь нашим меню 👇"
        )
    else:
        caption = (
            f"О, снова вы, {name}! 👀\n\n"
            f"Иголочка рада вас видеть!\n"
            f"Расскажите что случилось, или загляните в меню 👇"
        )
    
    temp_msg = await update.message.reply_text("🪡", reply_markup=remove_keyboard())
    await temp_msg.delete()
    
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    await update.message.reply_text(
        "📖 *Справка по боту*\n\n"
        "Используйте кнопку *Меню* слева от поля ввода для навигации.\n\n"
        "Доступные команды:\n"
        "/start — главный экран\n"
        "/order — оформить заказ\n"
        "/services — услуги и цены\n"
        "/contact — контакты\n"
        "/help — эта справка\n\n"
        f"📞 {WORKSHOP_PHONE}\n"
        f"📍 {WORKSHOP_ADDRESS}",
        parse_mode="Markdown"
    )
