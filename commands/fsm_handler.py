#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик FSM состояний для анонимок, песен, оценок и промо
"""

import os
from telegram import Update
from telegram.ext import ContextTypes

# Импорт состояний из callback_handler
from commands.callback_handler import user_states, ANON_STATE, SONG_STATE, RATE_LINK_STATE, PROMOTE_STATE

# Импорт функций отправки админам
from commands.admin_notifications import send_moderation_request, send_anon_with_photo, send_anon_with_voice

async def handle_fsm_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик FSM состояний"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # Проверяем, что это личное сообщение
    if chat_type != "private":
        return
    
    # FSM: если пользователь пишет анонимку
    if user_states.get(user_id) == ANON_STATE:
        print(f"Пользователь {user_id} в ANON_STATE. Проверка типа сообщения.")
        if update.message.text:
            # Обработка текстовых сообщений
            text = update.message.text.strip()
            anon_text = f"{text}\n\n#анон"
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "анонимка", user_info, anon_text)
            print(f"Новая анонимка на модерацию от {user_info}:\n{anon_text}")
            await update.message.reply_text("Спасибо! Ваша анонимка отправлена на модерацию.")
            user_states.pop(user_id, None)
            return

    # FSM: если пользователь предлагает песню
    elif user_states.get(user_id) == SONG_STATE:
        print(f"Пользователь {user_id} в SONG_STATE. Обработка сообщения.")
        song_info = update.message.text.strip()
        if song_info:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "песня", user_info, song_info)
            print(f"Новая песня предложена от {user_info}:\n{song_info}")
            await update.message.reply_text("Спасибо! Ваша песня отправлена администраторам.")
            user_states.pop(user_id, None)
            return
        else:
            await update.message.reply_text("Пожалуйста, отправьте название или ссылку на песню.")
            return
            
    # FSM: если пользователь отправляет ссылку для оценки
    elif user_states.get(user_id) == RATE_LINK_STATE:
        print(f"Пользователь {user_id} в RATE_LINK_STATE. Обработка сообщения.")
        rate_link = update.message.text.strip()
        if rate_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "оценка", user_info, rate_link)
            print(f"Новая ссылка для оценки от {user_info}:\n{rate_link}")
            await update.message.reply_text("Спасибо! Ваша ссылка отправлена администраторам для оценки.")
            user_states.pop(user_id, None)
            return
        else:
            await update.message.reply_text("Пожалуйста, отправьте ссылку на трек для оценки.")
            return
            
    # FSM: если пользователь отправляет ссылку для промо
    elif user_states.get(user_id) == PROMOTE_STATE:
        print(f"Пользователь {user_id} в PROMOTE_STATE. Обработка сообщения.")
        promote_link = update.message.text.strip()
        if promote_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "промо", user_info, promote_link)
            print(f"Новый запрос на промо от {user_info}:\n{promote_link}")
            await update.message.reply_text("Спасибо! Ваш запрос на промо отправлен на модерацию.")
            user_states.pop(user_id, None)
            return
        else:
            await update.message.reply_text("Пожалуйста, отправьте ссылку на трек для промо.")
            return

async def handle_anon_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных фотографий"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == ANON_STATE:
        print(f"Получена фотография от {user_id} в ANON_STATE.")
        # Обработка фотографий
        photo_id = update.message.photo[-1].file_id  # Берем последнюю (самую большую) версию фото
        caption = update.message.caption or ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            await send_anon_with_photo(context, user_info, photo_id, caption)
            print(f"Анонимная фотография от {user_info} успешно отправлена на модерацию")
            await update.message.reply_text("Спасибо! Ваша анонимная фотография отправлена на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке фото админам: {e}")
            await update.message.reply_text("Произошла ошибка при отправке фотографии. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

async def handle_anon_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных голосовых сообщений"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == ANON_STATE:
        print(f"Получено голосовое сообщение от {user_id} в ANON_STATE.")
        # Обработка голосовых сообщений
        voice_id = update.message.voice.file_id
        caption = update.message.caption or ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            await send_anon_with_voice(context, user_info, voice_id, caption)
            print(f"Анонимное голосовое сообщение от {user_info} успешно отправлено на модерацию")
            await update.message.reply_text("Спасибо! Ваше анонимное голосовое сообщение отправлено на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке голосового сообщения админам: {e}")
            await update.message.reply_text("Произошла ошибка при отправке голосового сообщения. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return
