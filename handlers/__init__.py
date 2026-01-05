"""
Пакет обработчиков для Telegram бота швейного HUBа.
Содержит все основные модули бота.
"""

from handlers import admin
from handlers import commands
from handlers import messages
from handlers import orders
from handlers import reviews

__all__ = ['admin', 'commands', 'messages', 'orders', 'reviews']

# Версия пакета
__version__ = '1.0.0'
__author__ = 'Швейный HUB'
__description__ = 'Telegram бот для мастерской Швейный HUB'
