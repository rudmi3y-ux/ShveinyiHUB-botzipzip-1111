#!/bin/bash
# Точка входа для Bothost.ru (Python-приложение).
# Bothost запускает указанную команду в корне загруженного репозитория.
# Переменные окружения (BOT_TOKEN, ADMIN_ID и др.) задаются в панели управления.
cd "$(dirname "$0")"

# Bothost выделяет порт через переменную PORT — под него поднимаем веб-админку.
export FLASK_PORT="${PORT:-8080}"

# На Bothost всегда один экземпляр приложения — локальный сокет-замок не нужен.
export DISABLE_INSTANCE_LOCK=1

exec python main.py
