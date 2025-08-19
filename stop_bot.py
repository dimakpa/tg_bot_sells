#!/usr/bin/env python3
"""
Скрипт для остановки бота
"""

import os
import signal
import psutil
from loguru import logger


def stop_bot():
    """Остановить бота"""
    logger.info("Останавливаем бота...")
    
    # Ищем процесс Python с main.py
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'main.py' in ' '.join(cmdline):
                logger.info(f"Найден процесс бота (PID: {proc.info['pid']})")
                proc.terminate()
                proc.wait(timeout=5)
                logger.info("✅ Бот остановлен")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue
    
    logger.warning("❌ Процесс бота не найден")
    return False


if __name__ == "__main__":
    stop_bot()
