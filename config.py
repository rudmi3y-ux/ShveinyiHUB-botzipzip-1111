"""
Централизованная конфигурация бота «Швейный HUB».

Все контактные данные мастерской и параметры окружения собираются здесь,
чтобы исключить дублирование в main.py, handlers/orders.py и других модулях.
"""
import os

from dotenv import load_dotenv

# Принудительно загружаем .env, чтобы игнорировать старые токены хостинга
load_dotenv(override=True)

# --- Информация о мастерской ---
WORKSHOP_INFO = {
    "name": "Швейная мастерская",
    "address": ("г. Москва, (МЦД/м. Ховрино) ул. Маршала Федоренко д.12, "
                "ТЦ \"Бусиново\", 1 этаж"),
    "phone": "+7 (968) 396-91-52",
    "whatsapp": "+7 (968) 396-91-52",
}

# Обратная совместимость / удобные алиасы
WORKSHOP_ADDRESS = WORKSHOP_INFO["address"]
WORKSHOP_PHONE = WORKSHOP_INFO["phone"]

HOURS_TEXT = "Пн-Чт: 10:00-19:50\nПт: 10:00-19:00\nСб: 10:00-17:00\nВс: выходной"

# Часы работы по дням недели (0=Пн, 6=Вс)
WORK_HOURS = {
    0: "10:00-19:50",  # Пн
    1: "10:00-19:50",  # Вт
    2: "10:00-19:50",  # Ср
    3: "10:00-19:50",  # Чт
    4: "10:00-19:00",  # Пт
    5: "10:00-17:00",  # Сб
    6: None,           # Вс - выходной
}

# --- Прочие настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
FLASK_PORT = int(os.getenv("FLASK_PORT", "8080"))
LOCK_PORT = int(os.getenv("LOCK_PORT", "48975"))
DISABLE_INSTANCE_LOCK = os.getenv("DISABLE_INSTANCE_LOCK", "0") == "1"

# Ссылка на карточку организации в Яндекс.Картах (для отзывов)
YANDEX_MAPS_ORG_URL = "https://yandex.ru/maps/org/shveyny_hub/1233246900"
YANDEX_REVIEWS_URL = YANDEX_MAPS_ORG_URL + "?si=qazrp3fnzwhkjgancr36aquutw"

# Координаты мастерской (ТЦ "Бусиново")
WORKSHOP_LOCATION = (55.870, 37.492)
