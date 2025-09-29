#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Отправка уведомлений администраторам
"""

import os
from telegram.ext import ContextTypes

# Получаем список админов из переменных окружения
def get_admin_ids():
    """Получение списка админов из переменных окружения"""
    admins_str = os.getenv('ADMINS', '')
    print(f"🔍 DEBUG: ADMINS строка = '{admins_str}'")
    
    if admins_str:
        admin_ids = [int(uid.strip()) for uid in admins_str.split(',') if uid.strip()]
        print(f"🔍 DEBUG: Распарсенные ID админов = {admin_ids}")
        return admin_ids
    else:
        print(f"🔍 DEBUG: Строка ADMINS пустая")
        return []

async def send_to_admins(context: ContextTypes.DEFAULT_TYPE, message: str, admin_ids: list = None):
    """Отправка сообщения всем админам"""
    if not admin_ids:
        admin_ids = get_admin_ids()
    
    if not admin_ids:
        print(f"⚠️ Нет админов для отправки сообщения: {message}")
        return
    
    sent_count = 0
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='HTML'
            )
            sent_count += 1
            print(f"✅ Сообщение отправлено админу {admin_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки админу {admin_id}: {e}")
    
    print(f"📤 Сообщение отправлено {sent_count} из {len(admin_ids)} админов")

async def send_moderation_request(context: ContextTypes.DEFAULT_TYPE, request_type: str, user_info: str, content: str):
    """Отправка запроса на модерацию"""
    emoji_map = {
        'анонимка': '🕵️',
        'песня': '🎶', 
        'оценка': '🎧',
        'промо': '📢'
    }
    
    emoji = emoji_map.get(request_type, '📝')
    message = (
        f"{emoji} <b>Новый запрос на модерацию:</b>\n\n"
        f"<b>Тип:</b> {request_type.title()}\n"
        f"<b>От пользователя:</b> {user_info}\n"
        f"<b>Содержание:</b>\n{content}\n\n"
        f"<i>Требует модерации</i>"
    )
    
    await send_to_admins(context, message)

async def send_anon_with_photo(context: ContextTypes.DEFAULT_TYPE, user_info: str, photo_file_id: str, caption: str = ""):
    """Отправка анонимной фотографии админам"""
    message = (
        f"🕵️ <b>Анонимная фотография:</b>\n\n"
        f"<b>От пользователя:</b> {user_info}\n"
    )
    
    if caption:
        message += f"<b>Подпись:</b> {caption}\n\n"
    
    message += "<i>Требует модерации</i>"
    
    admin_ids = get_admin_ids()
    for admin_id in admin_ids:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=message,
                parse_mode='HTML'
            )
            print(f"✅ Анонимная фотография отправлена админу {admin_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки анонимной фотографии админу {admin_id}: {e}")

async def send_anon_with_voice(context: ContextTypes.DEFAULT_TYPE, user_info: str, voice_file_id: str, caption: str = ""):
    """Отправка анонимного голосового сообщения админам"""
    message = (
        f"🕵️ <b>Анонимное голосовое сообщение:</b>\n\n"
        f"<b>От пользователя:</b> {user_info}\n"
    )
    
    if caption:
        message += f"<b>Подпись:</b> {caption}\n\n"
    
    message += "<i>Требует модерации</i>"
    
    admin_ids = get_admin_ids()
    for admin_id in admin_ids:
        try:
            await context.bot.send_voice(
                chat_id=admin_id,
                voice=voice_file_id,
                caption=message,
                parse_mode='HTML'
            )
            print(f"✅ Анонимное голосовое сообщение отправлено админу {admin_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки анонимного голосового сообщения админу {admin_id}: {e}")
