#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /help
"""

from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📋 **Доступные команды:**

**Основные:**
/start - запуск бота и кнопочное меню
/help - показать это сообщение
/nassal2026 - регистрация на конкурс NASSAL2026

**Развлечения:**
/prediction - получить вокальное предсказание
/random - случайная русская песня с Last.fm
/cat - случайное изображение котика
/meme - случайный мем
/casino - игра в слоты
/pole - игра "Поле чудес"
/ask [вопрос] - задать вопрос AI-персонажу

**Зал славы/позора:**
/hall [legend/cringe] [имя] - номинировать пользователя
/halllist - посмотреть списки
/vote [legend/cringe] [имя] - проголосовать

**Критика и подтверждение:**
/roast - получить критику исполнения
/proof - подтвердить исполнение

**В личных сообщениях:**
- /start - показывает кнопочное меню с функциями
- Бот отвечает на любые вопросы
- Доступны все команды через кнопки
        """
    await update.message.reply_text(help_text, parse_mode='Markdown')
