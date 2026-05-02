#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик callback'ов для кнопочного меню
"""

import asyncio
import os
import time
import random
import requests
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from commands.common import build_binary_stream
from commands.entertainment import get_random_russian_song

# FSM состояния
ANON_STATE = 'anon_waiting_text'
SONG_STATE = 'song_waiting_text'
RATE_LINK_STATE = 'rate_waiting_link'
PROMOTE_STATE = 'promote_waiting_link'
NASSAL_NAMES_STATE = 'nassal_waiting_names'
NASSAL_AVATAR_STATE = 'nassal_waiting_avatar'
NASSAL_CATEGORY_STATE = 'nassal_waiting_category'
NASSAL_CONFIRM_STATE = 'nassal_waiting_confirm'

# Словари для отслеживания времени последнего запроса
last_song_day_time = {}

# Глобальный словарь состояний пользователей
user_states = {}


async def send_cached_photo_or_message(context, chat_id: int, image_path: str, response_text: str):
    """Отправляет закэшированное изображение или текстовый fallback."""
    photo = build_binary_stream(image_path)
    if photo:
        await context.bot.send_photo(chat_id, photo, caption=response_text)
    else:
        await context.bot.send_message(chat_id, response_text)


def fetch_song_of_the_day():
    smule_performances_url = os.getenv('SMULE_PERFORMANCES_URL', '').strip()
    smule_account_id = os.getenv('SMULE_ACCOUNT_ID', '').strip()
    default_account_id = smule_account_id or '96242367'
    default_smule_api_url = (
        'https://www.smule.com/api/profile/performances'
        f'?accountId={default_account_id}&appUid=sing&offset=0&limit=12'
    )

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': 'https://www.smule.com/',
        'Origin': 'https://www.smule.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
    }

    request_url = smule_performances_url or default_smule_api_url
    if '_hot_dsip/performances/json' in request_url:
        request_url = default_smule_api_url

    session = requests.Session()
    session.headers.update(headers)
    session.cookies.set('app', 'sing', domain='www.smule.com')
    resp = session.get(request_url, timeout=10)
    resp.raise_for_status()
    return resp.json()

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'ов от кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    
    print(f"Callback query received: {query.data} from user {query.from_user.username or query.from_user.id} in chat {chat_id}")
    
    if query.data == "button1":
        # Анонимка
        user_states[user_id] = ANON_STATE
        print(f"Установлено состояние ANON_STATE для пользователя {user_id}")
        response_text = "Отправьте текст, фотографию или голосовое сообщение для анонимки:"
        image_path = 'images/anon.png'
        
        try:
            await send_cached_photo_or_message(context, chat_id, image_path, response_text)
        except Exception as e:
            print(f"Ошибка при отправке картинки или текста для кнопки Анонимка: {e}")
            await context.bot.send_message(chat_id, response_text)
            
    elif query.data == "button2":
        # Предложить песню
        user_states[user_id] = SONG_STATE
        response_text = "Введи название песни или ссылку на неё. Можно добавить теги (например: #дуэт #челлендж #классика):"
        image_path = 'images/sing.png'
        
        try:
            await send_cached_photo_or_message(context, chat_id, image_path, response_text)
        except Exception as e:
            print(f"Ошибка при отправке картинки или текста для кнопки Предложить песню: {e}")
            await context.bot.send_message(chat_id, response_text)
            
    elif query.data == "button3":
        # Оценить исполнение
        user_states[user_id] = RATE_LINK_STATE
        response_text = "Отправь ссылку на свой трек в Smule:"
        image_path = 'images/rate.png'
        
        try:
            await send_cached_photo_or_message(context, chat_id, image_path, response_text)
        except Exception as e:
            print(f"Ошибка при отправке картинки или текста для кнопки Оценить исполнение: {e}")
            await context.bot.send_message(chat_id, response_text)
            
    elif query.data == "button4":
        # Песня дня
        now = time.time()
        if user_id in last_song_day_time and now - last_song_day_time[user_id] < 5:
            print(f"Песня дня — лимит для {user_id}")
            await context.bot.send_message(chat_id, "Можно использовать не чаще 1 раза в 5 секунд!")
            return
        last_song_day_time[user_id] = now
        
        try:
            data = await asyncio.to_thread(fetch_song_of_the_day)
            songs = data.get('list', [])
            if not songs:
                raise RuntimeError("Smule не вернул список песен")
            song = random.choice(songs)
            title = song.get('title', 'Без названия')
            artist = song.get('artist', '')
            web_url = song.get('web_url', '')
            cover_url = song.get('cover_url', '')
            song_url = web_url
            if song_url and song_url.startswith('/'):
                song_url = f"https://www.smule.com{song_url}"
            msg = f"🎲 Песня дня:\n<b>{title}</b> — {artist}"
            if song_url:
                msg += f"\n{song_url}"
            print(f"Песня дня для {user_id}: {title} — {artist}")
            if cover_url:
                await context.bot.send_photo(chat_id, cover_url, caption=msg, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id, msg, parse_mode='HTML')
        except Exception as e:
            print(f"Ошибка при получении песни дня: {e}")
            fallback_title, fallback_artist, fallback_link = await asyncio.to_thread(get_random_russian_song)
            if fallback_title:
                fallback_msg = (
                    f"🎲 Песня дня:\n<b>{fallback_title}</b> — {fallback_artist}\n{fallback_link}"
                )
                await context.bot.send_message(chat_id, fallback_msg, parse_mode='HTML')
            else:
                await context.bot.send_message(
                    chat_id,
                    "Не удалось получить песню дня ни из Smule, ни из резервного источника."
                )
            
    elif query.data == "button6":
        # Промо
        user_states[user_id] = PROMOTE_STATE
        response_text = "Отправьте ссылку на трек, который хотите пропиарить:"
        image_path = 'images/piar.png'
        
        try:
            await send_cached_photo_or_message(context, chat_id, image_path, response_text)
        except Exception as e:
            print(f"Ошибка при отправке картинки или текста для кнопки Промо: {e}")
            await context.bot.send_message(chat_id, response_text)

    elif query.data == "button_nassal2026":
        from commands.nassal2026 import start_nassal_registration

        try:
            await start_nassal_registration(update, context)
        except Exception as e:
            print(f"Ошибка при запуске регистрации NASSAL2026: {e}")
            await context.bot.send_message(
                chat_id,
                "🏆 Добро пожаловать на конкурс NASSAL2026!\n\nНапишите, пожалуйста, одно имя или два имени участников."
            )

    elif query.data == "nassal_show_status":
        from storage.s3_registry import load_registration_rows
        from commands.nassal2026 import send_baskets_status_message

        try:
            registrations = await asyncio.to_thread(load_registration_rows)
            await send_baskets_status_message(context, chat_id, registrations)
        except Exception as e:
            print(f"Ошибка при загрузке состояния корзин NASSAL2026: {e}")
            await context.bot.send_message(
                chat_id,
                "Не удалось загрузить состояние корзин. Попробуйте чуть позже."
            )

    elif query.data == "nassal_delete_registration":
        from storage.s3_registry import delete_registration_by_user_id

        try:
            deleted_registration = await asyncio.to_thread(delete_registration_by_user_id, user_id)
            context.user_data.pop("nassal_registration", None)
            user_states.pop(user_id, None)
            if deleted_registration is None:
                await context.bot.send_message(
                    chat_id,
                    "Похоже, активная регистрация уже не найдена."
                )
            else:
                await context.bot.send_message(
                    chat_id,
                    "🗑️ Ваша регистрация на NASSAL2026 удалена.\n\n"
                    "Если захотите зарегистрироваться заново, просто отправьте /nassal2026."
                )
        except Exception as e:
            print(f"Ошибка при удалении регистрации NASSAL2026: {e}")
            await context.bot.send_message(
                chat_id,
                "Не удалось удалить регистрацию. Попробуйте чуть позже."
            )
    if '_hot_dsip/performances/json' in smule_performances_url:
        smule_performances_url = ''
