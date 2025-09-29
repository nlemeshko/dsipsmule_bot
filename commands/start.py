#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /start с кнопочным меню
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        # Создаем кнопочное меню для личных сообщений
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🕵 Анонимка", callback_data="button1"),
                InlineKeyboardButton("🎶 Песня", callback_data="button2")
            ],
            [
                InlineKeyboardButton("🎧 Оценить", callback_data="button3"),
                InlineKeyboardButton("🎲 Песня дня", callback_data="button4")
            ],
            [
                InlineKeyboardButton("📢 Промо", callback_data="button6")
            ]
        ])
        
        message = """🗡️ Привет. Я Геральт из Ривии. Ведьмак. 

Похоже, у нас здесь новый заказ — развлечь этот чат и навести порядок.
Выбирай, что будем делать:

**Контракты:**
• 🕵 Анонимка — передам записку без лишних вопросов
• 🎶 Песня — предложи трек, добавим в архив
• 🎧 Оценить — пришли ссылку, скажем честно
• 🎲 Песня дня — что подсоветует Судьба сегодня
• 📢 Промо — поможем громко заявить о себе

Если потеряешься — зови через /help. Я рядом."""
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
        
    elif chat_type == "channel":
        message = "🗡️ Бот Ведьмака активен в канале. Используйте /help для списка контрактов."
        await update.message.reply_text(message)
        
    elif chat_type in ["group", "supergroup"]:
        message = "🗡️ Геральт на связи. Запускайте /help — выберем контракт."
        await update.message.reply_text(message)
    
    else:
        message = "🗡️ Геральт здесь. Воспользуйся /help — там весь список возможностей."
        await update.message.reply_text(message)
