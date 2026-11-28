#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram бот для канала и группы
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, MenuButtonWebApp, WebAppInfo
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
from commands.ai import AIRuntime, draw_command, transcribe_command, private_audio, group_message
from commands.fun import ded_command, passport_command, order_command, guess_command, mood_command, fun_callback
from commands.titles import verdict_command, titles_command, titles_callback, worker as titles_worker
from commands.callback_handler import handle_callback_query
from commands.fsm_handler import handle_fsm_message, handle_anon_photo
from miniapp.auth import miniapp_url
from miniapp.locks import locked_private

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Убираем шум от polling HTTP-запросов Telegram API, сохраняя INFO-логи самого бота.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Получаем токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

class TelegramBot:
    def __init__(self):
        self.mini_app_url = miniapp_url(os.getenv('MINI_APP_URL', ''))
        self.mini_app_server = None
        self.application = (Application.builder().token(BOT_TOKEN)
                            .post_init(self.post_init).post_stop(self.post_stop).build())
        # Mark the boundary before polling: queued messages from downtime are never AI inputs.
        self.application.bot_data["ai_runtime"] = AIRuntime()
        self.setup_handlers()

    async def post_init(self, application):
        from storage.hall import initialize_hall_storage
        try:
            await asyncio.to_thread(initialize_hall_storage)
        except Exception as exc:
            logger.error("Hall storage initialization failed: %s", type(exc).__name__)
        from storage.fun import initialize_storage
        try:
            state = await asyncio.to_thread(initialize_storage)
            application.bot_data["fun_ready"] = True
            import time
            application.bot_data["fun_games_active"] = {
                int(chat_id) for chat_id, game in state["games"].items()
                if not game.get("finished") and game["until"] > time.time()
            }
            application.bot_data["title_pending"] = {
                token: (poll["until"] if poll["message_id"] and not poll["closed"] else 0)
                for token, poll in state["community"].get("title_polls", {}).items() if not poll["reported"]
            }
        except Exception as exc:
            logger.error("Community storage initialization failed: %s", type(exc).__name__)
        application.bot_data["title_worker"] = asyncio.create_task(titles_worker(application))
        if self.mini_app_url:
            from miniapp.server import MiniAppServer
            self.mini_app_server = MiniAppServer(application, BOT_TOKEN)
            await self.mini_app_server.start()
            await application.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Открыть приложение", web_app=WebAppInfo(self.mini_app_url),
            ))
            logger.info("Mini App: %s", self.mini_app_url)
        else:
            logger.warning("MINI_APP_URL не задан: используется прежнее меню бота")

    async def post_stop(self, application):
        task = application.bot_data.pop("title_worker", None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.mini_app_server:
            await self.mini_app_server.stop()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Separate group: log every message before AI, FSM or games consume it.
        self.application.add_handler(MessageHandler(filters.ALL, self.log_message), group=-2)
        # Основные команды
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        self.application.add_handler(CommandHandler("app", start_command))
        
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
        self.application.add_handler(CommandHandler("draw", draw_command))
        self.application.add_handler(CommandHandler("transcribe", transcribe_command))
        self.application.add_handler(CommandHandler("ded", ded_command))
        self.application.add_handler(CommandHandler("passport", passport_command))
        self.application.add_handler(CommandHandler("order", order_command))
        self.application.add_handler(CommandHandler("guess", guess_command))
        self.application.add_handler(CommandHandler("mood", mood_command))
        self.application.add_handler(CommandHandler("verdict", verdict_command))
        self.application.add_handler(CommandHandler("titles", titles_command))
        # Before games handle (and possibly finish) a turn, so AI can skip active games.
        self.application.add_handler(MessageHandler(
            filters.ChatType.GROUPS & (filters.TEXT | filters.VOICE) & ~filters.COMMAND,
            group_message), group=-1)
        
        # Обработчик callback'ов от кнопок
        self.application.add_handler(CallbackQueryHandler(fun_callback, pattern=r"^fun:"))
        self.application.add_handler(CallbackQueryHandler(titles_callback, pattern=r"^titles:"))
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
            MessageHandler(filters.ChatType.PRIVATE & filters.VOICE, private_audio)
        )

        self.application.add_handler(
            MessageHandler(filters.ChatType.PRIVATE & filters.AUDIO, private_audio)
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
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
        for handlers in self.application.handlers.values():
            for handler in handlers:
                handler.callback = locked_private(handler.callback)
    
    async def log_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log the real sender and media type, including messages without text."""
        message, chat = update.effective_message, update.effective_chat
        if not message or not chat:
            return
        media_types = {
            "voice": "голосовое", "audio": "аудиофайл", "photo": "фото",
            "video": "видео", "video_note": "видеосообщение", "animation": "анимация",
            "document": "документ", "sticker": "стикер", "poll": "опрос",
            "location": "геопозиция", "contact": "контакт", "dice": "кубик",
        }
        kind = "текст" if message.text is not None else next(
            (label for field, label in media_types.items() if getattr(message, field, None)),
            "служебное сообщение",
        )
        content = message.text or message.caption or f"[{kind}]"
        sender_chat = message.sender_chat
        user = update.effective_user
        if sender_chat:
            sender = f"от имени чата {sender_chat.title or sender_chat.id} (sender_chat_id={sender_chat.id})"
        elif user:
            username = f" (@{user.username})" if user.username else ""
            sender = f"от {user.first_name or 'Неизвестный'}{username}"
        else:
            sender = "без пользователя"
        logger.info("Сообщение %s в %s (chat_id=%s, message_id=%s, тип=%s): %s",
                    sender, chat.type, chat.id, message.message_id, kind, content)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
    
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
