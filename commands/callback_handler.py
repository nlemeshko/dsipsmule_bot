#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик callback'ов для кнопочного меню
"""

import asyncio
import os
import time
import logging
import requests
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from commands.common import build_binary_stream
from commands.entertainment import get_random_russian_song
from commands.music import smule_song, song_message

logger = logging.getLogger(__name__)
_smule_retry_at = 0
_smule_source = None
# FSM состояния
ANON_STATE = 'anon_waiting_text'
SONG_STATE = 'song_waiting_text'
RATE_LINK_STATE = 'rate_waiting_link'
PROMOTE_STATE = 'promote_waiting_link'
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
    global _smule_retry_at, _smule_source
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

    if request_url != _smule_source:
        _smule_retry_at, _smule_source = 0, request_url
    if time.monotonic() < _smule_retry_at:
        raise RuntimeError('Smule temporarily unavailable')
    try:
        with requests.Session() as session:
            session.headers.update(headers)
            session.cookies.set('app', 'sing', domain='www.smule.com')
            resp = session.get(request_url, timeout=(3, 6))
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError('Invalid Smule response')
            return data
    except (requests.RequestException, ValueError):
        _smule_retry_at = time.monotonic() + 60
        raise

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
            title, artist, link, cover = smule_song(data)
        except (requests.RequestException, ValueError, TypeError, AttributeError, RuntimeError) as exc:
            logger.warning('Smule unavailable; using reserve music source (%s)', type(exc).__name__)
            title, artist, link = await asyncio.to_thread(get_random_russian_song)
            cover = ''
        if not title:
            await context.bot.send_message(chat_id, 'Не удалось подобрать песню. Попробуйте позже.')
            return
        msg = song_message('🎲 Песня дня:', title, artist, link)
        if cover:
            try:
                await context.bot.send_photo(chat_id, cover, caption=msg, parse_mode='HTML')
                return
            except Exception as exc:
                logger.warning('Song cover unavailable; sending the same song as text (%s)', type(exc).__name__)
        await context.bot.send_message(chat_id, msg, parse_mode='HTML')

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

    else:
        await context.bot.send_message(chat_id, "Это меню больше недоступно. Откройте приложение через /start.")
