#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /start с кнопочным меню
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from commands.common import build_binary_stream

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        # Создаем кнопочное меню для личных сообщений
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🏆 NASSAL2026", callback_data="button_nassal2026")
            ],
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
        
        message = """🏆 <b>NASSAL2026 уже здесь!</b>

Первой кнопкой я вынес регистрацию на конкурс, чтобы до неё можно было дотянуться сразу.
Если хочешь подать заявку, нажми <b>NASSAL2026</b> и я проведу тебя по шагам.

🗡️ А если нужен другой контракт, вот всё меню:

<b>Контракты:</b>
• 🕵 Анонимка — передам записку без лишних вопросов
• 🎶 Песня — предложи трек, добавим в архив
• 🎧 Оценить — пришли ссылку, скажем честно
• 🎲 Песня дня — что подсоветует Судьба сегодня
• 📢 Промо — поможем громко заявить о себе

Если потеряешься — зови через /help. Я рядом."""

        photo = build_binary_stream('images/nassal2026.png')
        if photo:
            await update.message.reply_photo(photo, caption=message, reply_markup=keyboard, parse_mode='HTML')
        else:
            await update.message.reply_text(message, reply_markup=keyboard, parse_mode='HTML')
        
    elif chat_type == "channel":
        message = "🗡️ Бот Ведьмака активен в канале. Используйте /help для списка контрактов."
        await update.message.reply_text(message)
        
    elif chat_type in ["group", "supergroup"]:
        message = "🗡️ Геральт на связи. Запускайте /help — выберем контракт."
        await update.message.reply_text(message)
    
    else:
        message = "🗡️ Геральт здесь. Воспользуйся /help — там весь список возможностей."
        await update.message.reply_text(message)
