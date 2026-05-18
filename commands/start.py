#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /start с кнопочным меню
"""

import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from commands.common import build_binary_stream
from storage.s3_registry import find_final_registration_by_user_id


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        final_registration = None
        try:
            final_registration = await asyncio.to_thread(find_final_registration_by_user_id, update.effective_user.id)
        except Exception:
            final_registration = None

        stage_button_text = "🏆 Финал" if final_registration is not None else "📝 Этап II"
        stage_button_callback = "button_nassal_final" if final_registration is not None else "button_nassal_first_stage"

        # Создаем кнопочное меню для личных сообщений
        keyboard_rows = [
            [
                InlineKeyboardButton(stage_button_text, callback_data=stage_button_callback)
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
        ]
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        message = """📝 <b>Этап II уже открыт!</b>

Первой кнопкой я вынес отправку работы для <b>Этапа II</b>, чтобы до неё можно было дотянуться сразу.
Теперь этот этап доступен всем.

🗡️ А если нужен другой контракт, вот всё меню:

<b>Контракты:</b>
• 🕵 Анонимка — передам записку без лишних вопросов
• 🎶 Песня — предложи трек, добавим в архив
• 🎧 Оценить — пришли ссылку, скажем честно
• 🎲 Песня дня — что подсоветует Судьба сегодня
• 📢 Промо — поможем громко заявить о себе

Если потеряешься — зови через /help. Я рядом."""

        photo = build_binary_stream('images/2stage.png')
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
