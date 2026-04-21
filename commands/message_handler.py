#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик личных сообщений
"""

from telegram import Update
from telegram.ext import ContextTypes
import random

# Список ответов для личных сообщений
PERSONAL_RESPONSES = [
    "Привет! Как дела? 😊",
    "Здравствуй! Чем могу помочь? 🤔",
    "Привет! Рад тебя видеть! 👋",
    "Здорово! Что нового? 😄",
    "Привет! Как настроение? 😊",
    "Здравствуй! Все хорошо? 👍",
    "Привет! Чем займемся? 🚀",
    "Здорово! Как дела? 😎",
    "Привет! Что расскажешь? 😊",
    "Здравствуй! Рад общению! 🤗"
]

async def handle_personal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик личных сообщений"""
    msg = update.effective_message
    if not msg or not msg.text:
        return
    user_message = msg.text.lower()
    user_name = update.effective_user.first_name
    
    # Проверяем, идет ли сейчас игра "Поле чудес" для этого пользователя
    from commands.pole import pole_games
    user_id = update.effective_user.id
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    
    if user_id in pole_games and pole_games[user_id]['chat_id'] == chat_id:
        # Если игра активна, передаем управление обработчику игры
        from commands.pole import handle_pole_message
        await handle_pole_message(update, context)
        return
    
    # Простые ответы на основе ключевых слов
    if any(word in user_message for word in ['привет', 'здравствуй', 'hi', 'hello']):
        response = f"Привет, {user_name}! 👋 Рад тебя видеть!"
    
    elif any(word in user_message for word in ['как дела', 'как ты', 'что нового']):
        response = "У меня все отлично! 😊 А у тебя как дела?"
    
    elif any(word in user_message for word in ['спасибо', 'благодарю', 'thanks']):
        response = "Пожалуйста! 😊 Всегда рад помочь!"
    
    elif any(word in user_message for word in ['пока', 'до свидания', 'bye']):
        response = f"Пока, {user_name}! 👋 Увидимся!"
    
    elif any(word in user_message for word in ['помощь', 'help', 'что умеешь']):
        response = """🤖 Я умею:
• Отвечать на команды в каналах и группах
• Общаться в личных сообщениях
• Помогать с различными вопросами

Попробуй команду /help для полного списка!"""
    
    elif any(word in user_message for word in ['бот', 'robot', 'искусственный']):
        response = "Да, я бот! 🤖 Но я стараюсь быть полезным и дружелюбным!"
    
    elif any(word in user_message for word in ['время', 'дата', 'день']):
        from datetime import datetime
        now = datetime.now()
        response = f"Сейчас {now.strftime('%H:%M, %d.%m.%Y')} 🕐"
    
    else:
        # Случайный ответ, если не найдено ключевых слов
        response = random.choice(PERSONAL_RESPONSES)
    
    await msg.reply_text(response)
