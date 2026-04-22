#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик FSM состояний для анонимок, песен, оценок и промо
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

# Импорт состояний из callback_handler
from commands.callback_handler import (
    user_states,
    ANON_STATE,
    SONG_STATE,
    RATE_LINK_STATE,
    PROMOTE_STATE,
    NASSAL_NAMES_STATE,
    NASSAL_AVATAR_STATE,
    NASSAL_CATEGORY_STATE,
    NASSAL_CONFIRM_STATE,
)

# Импорт функций отправки админам
from commands.admin_notifications import (
    send_moderation_request,
    send_anon_with_photo,
    send_anon_with_voice,
    send_photo_to_admins,
    send_to_admins,
)
from commands.nassal2026 import (
    NASSAL_BASKETS,
    NASSAL_AVATAR_TEXT,
    YES_ANSWERS,
    NO_ANSWERS,
    get_basket_full_name,
    send_category_guide,
    send_registration_summary,
    send_success_message,
)
from storage.s3_registry import (
    append_registration_row,
    build_registration_row,
    load_registration_rows,
)


logger = logging.getLogger(__name__)

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

    elif user_states.get(user_id) == NASSAL_NAMES_STATE:
        participants = msg.text.strip() if (msg and msg.text) else ""
        if not participants:
            await msg.reply_text("Пожалуйста, напишите одно имя или два имени участников текстом.")
            return

        context.user_data["nassal_registration"] = {
            "participants": participants,
        }
        user_states[user_id] = NASSAL_AVATAR_STATE
        await msg.reply_text(NASSAL_AVATAR_TEXT, parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_AVATAR_STATE:
        await msg.reply_text("Сейчас нужен аватар. Пришлите его одной фотографией.")
        return

    elif user_states.get(user_id) == NASSAL_CATEGORY_STATE:
        category_choice = msg.text.strip() if (msg and msg.text) else ""
        if category_choice not in NASSAL_BASKETS:
            await msg.reply_text(
                "Нужно отправить одно число: 1, 2, 3 или 4.\n\n"
                "1 — Корзина имени Гены Букина — Вокалисты\n"
                "2 — Корзина имени Светы Букиной — Рокеры\n"
                "3 — Корзина имени Ромы Букина — Реперы\n"
                "4 — Корзина имени Даши Букиной — Приколисты"
            )
            return

        registration = context.user_data.get("nassal_registration", {})
        registration["category_choice"] = category_choice
        user_states[user_id] = NASSAL_CONFIRM_STATE
        await send_registration_summary(context, msg.chat_id, registration)
        return

    elif user_states.get(user_id) == NASSAL_CONFIRM_STATE:
        answer = msg.text.strip().lower() if (msg and msg.text) else ""

        if answer in YES_ANSWERS:
            registration = context.user_data.get("nassal_registration", {})
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            full_name = update.effective_user.full_name or "Без имени"
            category_choice = registration["category_choice"]
            basket_full_name = get_basket_full_name(category_choice)
            admin_message = (
                "🏆 <b>Новая регистрация на конкурс NASSAL2026</b>\n\n"
                f"<b>Telegram:</b> {user_info}\n"
                f"<b>Имя в Telegram:</b> {full_name}\n"
                f"<b>Участник(и):</b> {registration['participants']}\n"
                f"<b>Корзина:</b> {basket_full_name}"
            )

            avatar_file_id = registration.get("avatar_file_id")
            if avatar_file_id:
                await send_photo_to_admins(context, avatar_file_id, admin_message)
            else:
                await send_to_admins(context, admin_message)

            s3_row = build_registration_row(
                user_id=user_id,
                username=update.effective_user.username,
                full_name=update.effective_user.full_name,
                participants=registration["participants"],
                category_code=category_choice,
                category_name=basket_full_name,
                avatar_file_id=avatar_file_id,
            )
            try:
                await asyncio.to_thread(append_registration_row, s3_row)
            except Exception as exc:
                logger.exception("Не удалось сохранить регистрацию в Object Storage: %s", exc)

            await send_success_message(context, msg.chat_id)
            context.user_data.pop("nassal_registration", None)
            user_states.pop(user_id, None)
            return

        if answer in NO_ANSWERS:
            context.user_data.pop("nassal_registration", None)
            user_states[user_id] = NASSAL_NAMES_STATE
            await msg.reply_text(
                "Хорошо, давай заполним заявку заново.\n\n"
                "Напиши одно имя или два имени участников для регистрации на NASSAL2026."
            )
            return

        await msg.reply_text("Ответьте, пожалуйста, <b>да</b> или <b>нет</b>.", parse_mode='HTML')
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
        
    if user_states.get(user_id) == NASSAL_AVATAR_STATE:
        photo_id = (msg.photo[-1].file_id if (msg and msg.photo) else None)
        if not photo_id:
            await msg.reply_text("Не удалось получить фото. Попробуйте отправить аватар ещё раз.")
            return

        registration = context.user_data.setdefault("nassal_registration", {})
        registration["avatar_file_id"] = photo_id
        user_states[user_id] = NASSAL_CATEGORY_STATE
        registrations = None
        try:
            registrations = await asyncio.to_thread(load_registration_rows)
        except Exception as exc:
            logger.exception("Не удалось загрузить регистрации из Object Storage: %s", exc)
        await send_category_guide(context, msg.chat_id, registrations=registrations)
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
