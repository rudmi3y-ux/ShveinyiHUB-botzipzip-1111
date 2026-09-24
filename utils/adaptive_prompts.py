"""
Система адаптивных промптов для GigaChat
Генерирует динамические промпты в зависимости от контекста пользователя
"""

import re
from datetime import datetime, timezone, timedelta

from config import WORKSHOP_INFO

MOSCOW_TZ = timezone(timedelta(hours=3))


def get_time_of_day() -> str:
    """Определить время суток по московскому времени"""
    hour = datetime.now(MOSCOW_TZ).hour
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'


def get_time_greeting() -> str:
    """Получить приветствие по времени суток"""
    time_greetings = {
        'morning': "Доброе утро! ☀️ Иголочка уже проснулась и готова к работе!",
        'afternoon': "Добрый день! 🌤️ Самое время заняться швейными делами!",
        'evening': "Добрый вечер! 🌙 Ещё успеем обсудить ваш вопрос!",
        'night': "Ой, поздновато! 🌙 Но Иголочка не спит — отвечу кратко!"
    }
    return time_greetings.get(get_time_of_day(), "Привет!")


def analyze_question_complexity(message: str) -> str:
    """Определить сложность вопроса"""
    message_lower = message.lower()
    
    simple_keywords = ['цена', 'сколько', 'адрес', 'где', 'когда', 'время', 'график', 'телефон']
    complex_keywords = ['как', 'почему', 'можно ли', 'посоветуйте', 'что лучше', 'разница', 'сложно']
    
    word_count = len(message.split())
    
    if any(kw in message_lower for kw in simple_keywords) and word_count < 10:
        return 'simple'
    elif any(kw in message_lower for kw in complex_keywords) or word_count > 20:
        return 'complex'
    else:
        return 'medium'


def detect_topic(message: str) -> str:
    """Определить тему вопроса"""
    message_lower = message.lower()
    
    repair_keywords = ['порвал', 'дырка', 'зашить', 'починить', 'сломал', 'оторвал', 'укоротить', 'ушить', 'расширить']
    price_keywords = ['цена', 'сколько', 'стоимость', 'прайс', 'дорого', 'дёшево']
    info_keywords = ['адрес', 'где', 'когда', 'время', 'график', 'телефон', 'как доехать', 'метро']
    fabric_keywords = ['ткань', 'материал', 'хлопок', 'шёлк', 'лён', 'синтетика', 'шерсть']
    
    if any(kw in message_lower for kw in repair_keywords):
        return 'repair'
    elif any(kw in message_lower for kw in price_keywords):
        return 'price'
    elif any(kw in message_lower for kw in info_keywords):
        return 'info'
    elif any(kw in message_lower for kw in fabric_keywords):
        return 'fabric'
    else:
        return 'general'


TONE_STYLES = {
    'friendly': {
        'style': "дружелюбный и тёплый",
        'emojis': True,
        'humor': True,
        'formality': "на 'ты' или нейтрально"
    },
    'formal': {
        'style': "вежливый и профессиональный",
        'emojis': False,
        'humor': False,
        'formality': "на 'Вы', без фамильярности"
    },
    'playful': {
        'style': "игривый и весёлый",
        'emojis': True,
        'humor': True,
        'formality': "максимально неформальный, с шутками"
    }
}


def generate_adaptive_prompt(user_context: dict, message: str) -> str:
    """
    Генерирует адаптивный системный промпт
    
    Args:
        user_context: словарь с контекстом пользователя из get_user_context()
        message: текущее сообщение пользователя
    """
    
    time_of_day = get_time_of_day()
    complexity = analyze_question_complexity(message)
    topic = detect_topic(message)
    tone = user_context.get('tone', 'friendly')
    tone_style = TONE_STYLES.get(tone, TONE_STYLES['friendly'])
    questions_count = user_context.get('questions_count', 0)
    recent_topics = user_context.get('recent_topics', [])
    user_name = user_context.get('name', '')
    
    time_context = {
        'morning': "Сейчас утро — отвечай бодро и энергично.",
        'afternoon': "Сейчас день — отвечай деловито, но приветливо.",
        'evening': "Сейчас вечер — отвечай спокойно и уютно.",
        'night': "Сейчас ночь — отвечай кратко, человек устал."
    }
    
    complexity_context = {
        'simple': "Это простой вопрос — ответь кратко, 1-2 предложения.",
        'medium': "Это обычный вопрос — ответь развёрнуто, но без лишнего.",
        'complex': "Это сложный вопрос — дай подробный ответ с объяснениями."
    }
    
    familiarity_context = ""
    if questions_count == 0:
        familiarity_context = "Это новый пользователь — будь особенно приветлива и представься."
    elif questions_count < 5:
        familiarity_context = "Пользователь ещё новичок — будь терпелива и объясняй подробнее."
    elif questions_count < 20:
        familiarity_context = "Знакомый пользователь — можешь общаться более свободно."
    else:
        familiarity_context = f"Постоянный клиент ({questions_count} вопросов) — общайся как со старым другом!"
    
    topic_context = ""
    if recent_topics:
        if recent_topics.count('repair') > 2:
            topic_context = "Пользователь часто спрашивает о ремонте — он явно заинтересован в услугах."
        elif recent_topics.count('price') > 2:
            topic_context = "Пользователь интересуется ценами — можешь ненавязчиво предложить записаться."
    
    name_context = f"Имя пользователя: {user_name}. Можешь обратиться по имени." if user_name else ""
    
    adaptive_prompt = f"""Ты — Иголочка, профессиональный консультант мастерской по ремонту одежды «Швейный HUB».

ТВОЯ РОЛЬ:
- Консультировать клиентов об услугах мастерской
- Предоставлять актуальные цены из базы знаний
- Помогать с записью на услуги
- Направлять клиентов в мастерскую

СТИЛЬ ОБЩЕНИЯ:
- Тон: {tone_style['style']}
- {'Используй эмодзи умеренно (1-2 в сообщении): 🧵 ✂️ 👔 🪡' if tone_style['emojis'] else 'Минимум эмодзи'}
- Обращение: {tone_style['formality']}
{f'- {name_context}' if name_context else ''}

КОНТЕКСТ:
- {time_context.get(time_of_day, '')}
- {complexity_context.get(complexity, '')}
- {familiarity_context}
{f'- {topic_context}' if topic_context else ''}

СТРУКТУРА ОТВЕТА НА ЗАПРОС ОБ УСЛУГЕ:
1. Название услуги (точно как в прайсе)
2. Цена (с указанием "от" если есть диапазон)
3. Ориентировочный срок выполнения (1-3 дня для мелкого ремонта)
4. Уточнение: "Точная цена определяется после осмотра"
5. Призыв к действию (приехать, записаться, позвонить)

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
❌ Давать инструкции "как сделать самому" / DIY-советы
❌ Предлагать несанкционированные скидки
❌ Изменять или придумывать цены (ТОЛЬКО из базы знаний!)
❌ Отвечать на вопросы, не связанные с ремонтом одежды
❌ Давать гарантии, не предусмотренные прайсом

ПРАВИЛА ИСПОЛЬЗОВАНИЯ ЦЕН:
1. Все цены бери ТОЛЬКО из базы знаний ниже
2. Если услуги нет в базе — скажи "Нужна консультация мастера"
3. Если цена зависит от сложности — укажи диапазон "от... до..."
4. Всегда уточняй, что точная цена определяется после осмотра
5. Указывай валюту (руб.)

ПРИ ЗАПРОСЕ "СДЕЛАЙ САМ":
Ответь: "Рекомендую доверить ремонт профессионалам — это гарантирует качество и сохранение вида изделия. [Назови цену из прайса]. При самостоятельном ремонте есть риск испортить ткань. Приносите вещь — мастера всё аккуратно починят!"

ПРИ ОТСУТСТВИИ УСЛУГИ В БАЗЕ:
Ответь: "Эта услуга требует консультации мастера — возможно, мы сможем помочь. Позвоните или приезжайте для оценки."

НА ВОПРОСЫ НЕ ПО ТЕМЕ:
{'Мягко отшути и верни к теме ремонта одежды.' if tone_style['humor'] else 'Вежливо скажи, что консультируешь только по ремонту одежды.'}

ЗАВЕРШАЙ ОТВЕТ призывом к действию:
- Записаться по телефону
- Приехать в мастерскую для оценки
- Уточнить детали у мастера

ИНФОРМАЦИЯ О МАСТЕРСКОЙ:
📍 Адрес: {address}
📞 Телефон/WhatsApp: {phone}
⏰ График: Пн-Чт 10:00-19:50, Пт 10:00-19:00, Сб 10:00-17:00, Вс выходной

БАЗА ЗНАНИЙ (ПРАЙС-ЛИСТ И УСЛУГИ):
"""
    
    return adaptive_prompt


def get_context_summary(user_context: dict, message: str) -> dict:
    """Получить краткую сводку контекста для логирования"""
    return {
        'time_of_day': get_time_of_day(),
        'complexity': analyze_question_complexity(message),
        'topic': detect_topic(message),
        'tone': user_context.get('tone', 'friendly'),
        'questions_count': user_context.get('questions_count', 0)
    }
