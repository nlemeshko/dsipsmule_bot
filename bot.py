#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram бот для канала и группы
"""

import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Импортируем команды из отдельных файлов
from commands.start import start_command
from commands.help import help_command
from commands.message_handler import handle_personal_message
from commands.prediction import prediction_command
from commands.hall import hall_command, halllist_command, vote_command
from commands.entertainment import random_command, cat_command, meme_command, casino_command
from commands.pole import pole_command, handle_pole_message
from commands.roast_proof import roast_command, proof_command
from commands.ask import ask_command
from commands.callback_handler import handle_callback_query
from commands.fsm_handler import handle_fsm_message, handle_anon_photo, handle_anon_voice

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

class TelegramBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        
        # Команды развлечений
        self.application.add_handler(CommandHandler("prediction", prediction_command))
        self.application.add_handler(CommandHandler("hall", hall_command))
        self.application.add_handler(CommandHandler("halllist", halllist_command))
        self.application.add_handler(CommandHandler("vote", vote_command))
        self.application.add_handler(CommandHandler("random", random_command))
        self.application.add_handler(CommandHandler("cat", cat_command))
        self.application.add_handler(CommandHandler("meme", meme_command))
        self.application.add_handler(CommandHandler("casino", casino_command))
        self.application.add_handler(CommandHandler("pole", pole_command))
        self.application.add_handler(CommandHandler("roast", roast_command))
        self.application.add_handler(CommandHandler("proof", proof_command))
        self.application.add_handler(CommandHandler("ask", ask_command))
        
        # Обработчик callback'ов от кнопок
        self.application.add_handler(CallbackQueryHandler(handle_callback_query))
        
        # Обработчик FSM состояний (только для private чатов)
        self.application.add_handler(
            MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
                         handle_fsm_message)
        )
        
        # Обработчик анонимных фотографий
        self.application.add_handler(
            MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, handle_anon_photo)
        )
        
        # Обработчик анонимных голосовых сообщений
        self.application.add_handler(
            MessageHandler(filters.ChatType.PRIVATE & filters.VOICE, handle_anon_voice)
        )
        
        # Обработчик личных сообщений (только для private чатов, если не в FSM)
        self.application.add_handler(
            MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
                         handle_personal_message)
        )
        
        # Обработчик сообщений для игры Поле чудес (для групп и супергрупп)
        self.application.add_handler(
            MessageHandler((filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.TEXT & ~filters.COMMAND, handle_pole_message)
        )
        
        # Логирование всех сообщений (В КОНЦЕ, чтобы не перехватывать обработку)
        self.application.add_handler(
            MessageHandler(filters.ALL, self.log_message)
        )
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    async def log_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Логирование всех сообщений"""
        chat_type = update.effective_chat.type
        user = update.effective_user
        message_text = update.message.text if update.message else "Нет текста"
        
        # Безопасная обработка пользователя
        if user:
            user_name = user.first_name or "Неизвестный"
            username = user.username or "Нет username"
            logger.info(f"Сообщение от {user_name} (@{username}) в {chat_type}: {message_text}")
        else:
            logger.info(f"Системное сообщение в {chat_type}: {message_text}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
        
        # Попытка отправить сообщение об ошибке пользователю
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="😅 Произошла ошибка при обработке сообщения. Попробуйте еще раз!"
                )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        logger.info("Бот поддерживает:")
        logger.info("- Команды в каналах и группах")
        logger.info("- Личные сообщения с умными ответами")
        logger.info("- Модульную структуру команд")
        self.application.run_polling()

def main():
    """Основная функция"""
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
