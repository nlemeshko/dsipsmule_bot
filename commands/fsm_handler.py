#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик FSM состояний для анонимок, песен, оценок и промо
"""

from telegram import Update
from telegram.ext import ContextTypes

# Импорт состояний из callback_handler
from commands.callback_handler import (
    user_states,
    ANON_STATE,
    SONG_STATE,
    RATE_LINK_STATE,
    PROMOTE_STATE,
    NASSAL_NICK_STATE,
    NASSAL_CATEGORY_STATE,
)

# Импорт функций отправки админам
from commands.admin_notifications import send_moderation_request, send_anon_with_photo, send_anon_with_voice, send_to_admins
from commands.nassal2026 import NASSAL_CATEGORY_TEXT, NASSAL_SUCCESS_TEXT, NASSAL_CATEGORY_LABELS

async def handle_fsm_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик FSM состояний"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    # Проверяем, что это личное сообщение
    if chat_type != "private":
        return
    
    # FSM: если пользователь пишет анонимку
    if user_states.get(user_id) == ANON_STATE:
        print(f"Пользователь {user_id} в ANON_STATE. Проверка типа сообщения.")
        if msg and msg.text:
            # Обработка текстовых сообщений
            text = msg.text.strip()
            anon_text = f"{text}\n\n#анон"
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "анонимка", user_info, anon_text)
            print(f"Новая анонимка на модерацию от {user_info}:\n{anon_text}")
            await msg.reply_text("Спасибо! Ваша анонимка отправлена на модерацию.")
            user_states.pop(user_id, None)
            return

    elif user_states.get(user_id) == NASSAL_NICK_STATE:
        smule_nick = msg.text.strip() if (msg and msg.text) else ""
        if not smule_nick:
            await msg.reply_text("Пожалуйста, напишите ваш ник в Smule текстом.")
            return

        context.user_data["nassal_registration"] = {
            "smule_nick": smule_nick,
        }
        user_states[user_id] = NASSAL_CATEGORY_STATE
        await msg.reply_text(NASSAL_CATEGORY_TEXT, parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_CATEGORY_STATE:
        category_choice = msg.text.strip() if (msg and msg.text) else ""
        if category_choice not in NASSAL_CATEGORY_LABELS:
            await msg.reply_text(
                "Нужно отправить одно число: 1, 2, 3 или 4.\n\n"
                "1 — вокалисты\n"
                "2 — реперы\n"
                "3 — рокеры\n"
                "4 — приколисты"
            )
            return

        registration = context.user_data.get("nassal_registration", {})
        smule_nick = registration.get("smule_nick")
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        full_name = update.effective_user.full_name or "Без имени"
        category_name = NASSAL_CATEGORY_LABELS[category_choice]

        admin_message = (
            "🏆 <b>Новая регистрация на конкурс NASSAL2026</b>\n\n"
            f"<b>Telegram:</b> {user_info}\n"
            f"<b>Имя:</b> {full_name}\n"
            f"<b>Smule nick:</b> {smule_nick}\n"
            f"<b>Корзина:</b> {category_choice} — {category_name}"
        )

        await send_to_admins(context, admin_message)
        await msg.reply_text(NASSAL_SUCCESS_TEXT, parse_mode='HTML')
        context.user_data.pop("nassal_registration", None)
        user_states.pop(user_id, None)
        return

    # FSM: если пользователь предлагает песню
    elif user_states.get(user_id) == SONG_STATE:
        print(f"Пользователь {user_id} в SONG_STATE. Обработка сообщения.")
        song_info = msg.text.strip() if (msg and msg.text) else ""
        if song_info:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "песня", user_info, song_info)
            print(f"Новая песня предложена от {user_info}:\n{song_info}")
            await msg.reply_text("Спасибо! Ваша песня отправлена администраторам.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте название или ссылку на песню.")
            return
            
    # FSM: если пользователь отправляет ссылку для оценки
    elif user_states.get(user_id) == RATE_LINK_STATE:
        print(f"Пользователь {user_id} в RATE_LINK_STATE. Обработка сообщения.")
        rate_link = msg.text.strip() if (msg and msg.text) else ""
        if rate_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "оценка", user_info, rate_link)
            print(f"Новая ссылка для оценки от {user_info}:\n{rate_link}")
            await msg.reply_text("Спасибо! Ваша ссылка отправлена администраторам для оценки.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте ссылку на трек для оценки.")
            return
            
    # FSM: если пользователь отправляет ссылку для промо
    elif user_states.get(user_id) == PROMOTE_STATE:
        print(f"Пользователь {user_id} в PROMOTE_STATE. Обработка сообщения.")
        promote_link = msg.text.strip() if (msg and msg.text) else ""
        if promote_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "промо", user_info, promote_link)
            print(f"Новый запрос на промо от {user_info}:\n{promote_link}")
            await msg.reply_text("Спасибо! Ваш запрос на промо отправлен на модерацию.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте ссылку на трек для промо.")
            return

async def handle_anon_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных фотографий"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == ANON_STATE:
        print(f"Получена фотография от {user_id} в ANON_STATE.")
        # Обработка фотографий
        photo_id = (msg.photo[-1].file_id if (msg and msg.photo) else None)  # Берем последнюю (самую большую) версию фото
        caption = (msg.caption or "") if msg else ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            if photo_id:
                await send_anon_with_photo(context, user_info, photo_id, caption)
            print(f"Анонимная фотография от {user_info} успешно отправлена на модерацию")
            await msg.reply_text("Спасибо! Ваша анонимная фотография отправлена на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке фото админам: {e}")
            if msg:
                await msg.reply_text("Произошла ошибка при отправке фотографии. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

async def handle_anon_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных голосовых сообщений"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == ANON_STATE:
        print(f"Получено голосовое сообщение от {user_id} в ANON_STATE.")
        # Обработка голосовых сообщений
        voice_id = msg.voice.file_id if (msg and msg.voice) else None
        caption = (msg.caption or "") if msg else ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            if voice_id:
                await send_anon_with_voice(context, user_info, voice_id, caption)
            print(f"Анонимное голосовое сообщение от {user_info} успешно отправлено на модерацию")
            await msg.reply_text("Спасибо! Ваше анонимное голосовое сообщение отправлено на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке голосового сообщения админам: {e}")
            if msg:
                await msg.reply_text("Произошла ошибка при отправке голосового сообщения. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return
