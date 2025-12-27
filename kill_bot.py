#!/usr/bin/env python3
"""
Скрипт для полной остановки всех экземпляров бота
"""

import os
import sys
import subprocess
import time

def kill_all_processes():
    """Жесткая остановка ВСЕХ процессов бота"""
    print("=" * 60)
    print("⚡ ПОЛНАЯ ОЧИСТКА СИСТЕМЫ ОТ ПРОЦЕССОВ БОТА")
    print("=" * 60)
    
    commands = [
        ("Остановка всех Python процессов", "pkill -9 python"),
        ("Остановка процессов main.py", "pkill -9 -f main.py"),
        ("Остановка процессов start_bot.py", "pkill -9 -f start_bot.py"),
        ("Остановка процессов бота", "pkill -9 -f bot"),
        ("Остановка процессов telegram", "pkill -9 -f telegram"),
        ("Очистка временных файлов", "rm -f /tmp/bot.lock /tmp/python* /tmp/*bot* 2>/dev/null || true"),
    ]
    
    for description, cmd in commands:
        print(f"\n🔧 {description}...")
        try:
            # We don't use sudo here as we are in a container/VM with specific permissions
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.stdout or result.stderr:
                print(f"   Вывод: {result.stdout.strip()}")
                if result.stderr and "No such process" not in result.stderr:
                    print(f"   Ошибка: {result.stderr.strip()}")
        except Exception as e:
            print(f"   Ошибка выполнения: {e}")
    
    # Заключительная проверка
    print("\n🔍 Финальная проверка процессов...")
    subprocess.run("ps aux | grep -E 'python|main.py|bot' | grep -v grep || echo '✅ Процессов не найдено'", 
                   shell=True)
    
    print("\n" + "=" * 60)
    print("✅ ОЧИСТКА ЗАВЕРШЕНА!")
    print("=" * 60)

if __name__ == "__main__":
    kill_all_processes()
