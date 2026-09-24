import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from utils.gigachat_api import get_ai_response
from utils.anti_spam import anti_spam
from utils.database import add_user, is_user_blocked, get_user_info
import static_texts as T
from keyboards import get_main_menu, get_ai_response_keyboard
from handlers.admin import is_user_admin

logger = logging.getLogger(__name__)

# Максимальная длина сообщения для обработки AI
MAX_MESSAGE_LENGTH = 1000


async def handle_message(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений от пользователей"""
    try:
        if not update.message or not update.message.text:
            await handle_non_text_message(update, context)
            return

        user = update.effective_user
        user_id = user.id
        text = update.message.text.strip()

        # Проверяем режим администратора (например, для рассылки)
        if await handle_admin_mode(update, context, user_id, text):
            return

        # Добавляем/обновляем пользователя в базе
        add_user(user_id=user_id,
                 username=user.username,
                 first_name=user.first_name,
                 last_name=user.last_name)

        # Проверяем, не заблокирован ли пользователь
        if is_user_blocked(user_id):
            logger.warning(
                f"Заблокированный пользователь {user_id} пытался отправить сообщение"
            )
            await update.message.reply_text(
                "🚫 Ваш доступ к боту ограничен. Пожалуйста, свяжитесь с администратором."
            )
            return

        # Проверяем на спам
        is_spam, spam_reason = anti_spam.is_spam(user_id, text)
        if is_spam:
            logger.warning(f"Спам от {user_id}: {spam_reason}")
            await update.message.reply_text(
                f"⚠️ {spam_reason}\n\nПожалуйста, подождите немного перед следующим сообщением.",
                reply_markup=get_main_menu())
            return

        # Ограничиваем длину сообщения для AI
        if len(text) > MAX_MESSAGE_LENGTH:
            await update.message.reply_text(
                f"📝 Ваше сообщение слишком длинное ({len(text)} символов). "
                f"Пожалуйста, сократите его до {MAX_MESSAGE_LENGTH} символов.")
            return

        # Логируем полученное сообщение
        user_info = get_user_info(user_id)
        username_display = f"@{user_info.username}" if user_info and user_info.username else user_info.first_name if user_info else f"Пользователь {user_id}"
        logger.info(
            f"Сообщение от {username_display} (ID: {user_id}): {text[:100]}..."
        )

        # Показываем индикатор "печатает"
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"Не удалось отправить ChatAction: {e}")

        # Получаем ответ от AI
        try:
            # Проверка на запрос отзыва
            review_keywords = ['как оставить отзыв', 'где оставить отзыв', 'написать отзыв', 'оставить отзыв']
            if any(keyword in text.lower() for keyword in review_keywords):
                response = "Будем очень благодарны за ваш отзыв! Вы можете оставить его на Яндекс Картах по ссылке: https://yandex.ru/maps/org/shveynyy_hub/204285863268/"
                keyboard = get_ai_response_keyboard()
            else:
                response, needs_human = await get_ai_response(text, user_id)
                # Формируем клавиатуру ответа
                keyboard = get_ai_response_keyboard()

            # Отправляем ответ
            await update.message.reply_text(
                f"💭 {response}",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

            # Логируем успешный ответ
            logger.info(f"AI ответил пользователю {user_id}")

        except Exception as e:
            logger.error(f"Ошибка при получении ответа от AI: {e}")
            await update.message.reply_text(T.AI_UNAVAILABLE_TEXT,
                                            reply_markup=get_main_menu())

    except Exception as e:
        logger.error(f"Критическая ошибка в обработке сообщения: {e}")
        await update.message.reply_text(
            "😔 Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.")


async def handle_admin_mode(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            user_id: int, text: str) -> bool:
    """Обработка режима администратора (например, для рассылки)"""
    try:
        if not is_user_admin(user_id):
            return False

        # Проверяем специальные административные команды
        if text.startswith('/'):
            # Пропускаем команды для обработки в других хендлерах
            return False

        # Проверяем режим рассылки
        if context.user_data.get('broadcast_mode'):
            from handlers.admin import broadcast_send
            await broadcast_send(update, context, text)
            return True

        # Проверяем режим ответа пользователю
        if context.user_data.get('reply_mode'):
            target_user_id = context.user_data.get('reply_to_user')
            if target_user_id:
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📨 Ответ от администратора:\n\n{text}")
                    await update.message.reply_text(
                        f"✅ Ответ отправлен пользователю {target_user_id}")
                    context.user_data.pop('reply_mode', None)
                    context.user_data.pop('reply_to_user', None)
                except Exception as e:
                    logger.error(
                        f"Не удалось отправить ответ пользователю: {e}")
                    await update.message.reply_text(
                        f"❌ Не удалось отправить ответ: {e}")
                return True

        # Другие режимы администратора можно добавить здесь
        return False

    except Exception as e:
        logger.error(f"Ошибка в обработке режима администратора: {e}")
        return False


async def handle_non_text_message(update: Update,
                                  context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка не текстовых сообщений (фото, документы и т.д.)"""
    try:
        user_id = update.effective_user.id
        message = update.message

        if message.photo:
            await message.reply_text(T.PHOTO_UNSUPPORTED_TEXT)

        elif message.document:
            await message.reply_text(T.DOCUMENT_RECEIVED_TEXT)

        elif message.voice or message.audio:
            await message.reply_text(T.VOICE_UNSUPPORTED_TEXT)

        elif message.sticker:
            # Можно просто проигнорировать или ответить шуткой
            if update.effective_user.is_bot:
                return
            await message.reply_text("😊 Спасибо за стикер!")

        elif message.contact or message.location:
            await message.reply_text(
                "📍 Спасибо за контактные данные! Я сохраню их для связи.\n\n"
                "Чем еще могу помочь?",
                reply_markup=get_main_menu())

    except Exception as e:
        logger.error(f"Ошибка при обработке не текстового сообщения: {e}")
        await update.message.reply_text(
            "Извините, у меня возникли проблемы с обработкой вашего сообщения. "
            "Попробуйте отправить текстовое сообщение.")


async def handle_callback_query(update: Update,
                                context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка callback-запросов от inline-кнопок"""
    try:
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        data = query.data

        logger.info(f"Callback от пользователя {user_id}: {data}")

        # Обработка различных callback-действий
        if data == 'contact_human':
            await query.edit_message_text(T.CONTACT_HUMAN_TEXT,
                                          parse_mode="Markdown")

        elif data == 'rate_response':
            await query.edit_message_text(
                "⭐ Спасибо за оценку! Ваше мнение очень важно для нас.\n\n"
                "Можете оставить более подробный отзыв через команду /review",
                parse_mode="Markdown")

        elif data == 'new_question':
            await query.edit_message_text(
                "❓ Задайте ваш новый вопрос:\n\n"
                "Я постараюсь помочь максимально подробно!")

        elif data.startswith('admin_'):
            # Административные действия
            if is_user_admin(user_id):
                await handle_admin_callback(query, context, data)
            else:
                await query.edit_message_text(
                    "❌ У вас нет прав для этого действия.")

    except Exception as e:
        logger.error(f"Ошибка в обработке callback-запроса: {e}")
        try:
            await query.edit_message_text(
                "⚠️ Произошла ошибка. Попробуйте еще раз.")
        except:
            pass


async def handle_admin_callback(query, context, data: str):
    """Обработка административных callback-запросов"""
    try:
        if data == 'admin_broadcast':
            context.user_data['broadcast_mode'] = True
            await query.edit_message_text(
                "✉️ *Режим рассылки активирован*\n\n"
                "Введите сообщение для рассылки всем пользователям.\n\n"
                "Для отмены отправьте /cancel",
                parse_mode="Markdown")

        elif data == 'admin_stats':
            from utils.database import get_statistics
            stats = get_statistics()

            stats_text = ("📊 *Статистика бота:*\n\n"
                          f"👥 Пользователей: {stats.get('total_users', 0)}\n"
                          f"📦 Заказов: {stats.get('total_orders', 0)}\n"
                          f"🆕 Новых: {stats.get('new_orders', 0)}\n"
                          f"🔄 В работе: {stats.get('in_progress', 0)}\n"
                          f"✅ Готовых: {stats.get('completed', 0)}\n"
                          f"📤 Выданных: {stats.get('issued', 0)}\n"
                          f"🚫 Заблокировано: {stats.get('blocked_users', 0)}")
            await query.edit_message_text(stats_text, parse_mode="Markdown")

        elif data == 'admin_orders':
            await query.edit_message_text(
                "📦 *Управление заказами*\n\n"
                "Выберите действие:\n"
                "• Просмотр новых заказов\n"
                "• Заказы в работе\n"
                "• Готовые заказы\n"
                "• Поиск заказа\n\n"
                "Используйте веб-панель для полного управления.",
                parse_mode="Markdown")

        elif data == 'admin_back_menu':
            from keyboards import get_admin_main_menu
            await query.edit_message_text(
                "🛠 *Панель администратора*\n\n"
                "Выберите раздел для управления:",
                reply_markup=get_admin_main_menu(),
                parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в обработке административного callback: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при выполнении действия.")


# Обработчик для inline-запросов (поиск)
async def handle_inline_query(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка inline-запросов (если бот поддерживает inline режим)"""
    try:
        query = update.inline_query.query

        if not query or len(query.strip()) < 2:
            return

        # Здесь можно добавить логику поиска услуг, FAQ и т.д.
        # Пока просто уведомляем, что inline режим не поддерживается

        from telegram import InlineQueryResultArticle, InputTextMessageContent

        results = [
            InlineQueryResultArticle(
                id='1',
                title="Швейный HUB",
                description="Нажмите чтобы открыть бота",
                input_message_content=InputTextMessageContent(
                    "🔍 Для использования бота перейдите в чат с @ваш_бот"))
        ]

        await update.inline_query.answer(results, cache_time=300)

    except Exception as e:
        logger.error(f"Ошибка в обработке inline-запроса: {e}")
