#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /help
"""

from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, *, miniapp=False):
    """Обработчик команды /help"""
    help_text = """
🗡️ **Ведьмак · DSIP Smule**
Официальный сайт: https://dsipsmule.one

📋 **Доступные команды:**

**Основные:**
/start или /app - открыть мини-приложение
/help - показать это сообщение

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

**В личных сообщениях:**
- /start - показывает кнопку открытия мини-приложения
- Бот отвечает на любые вопросы
- Доступны все команды через кнопки
        """
    if not miniapp:
        help_text = help_text.replace("**В личных сообщениях:**", "**Критика и подтверждение:**\n/roast - получить критику исполнения\n/proof - подтвердить исполнение\n\n**В личных сообщениях:**")
    await update.message.reply_text(help_text, parse_mode='Markdown')
