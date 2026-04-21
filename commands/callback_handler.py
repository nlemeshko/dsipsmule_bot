#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик callback'ов для кнопочного меню
"""

import asyncio
import time
import random
import requests
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from commands.common import build_binary_stream

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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
    }
    url = 'https://www.smule.com/api/profile/performances?accountId=96242367&appUid=sing&offset=0&limit=25'
    resp = requests.get(url, headers=headers, timeout=10)
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
                print("Не удалось получить список песен с Smule API")
                await context.bot.send_message(chat_id, "Не удалось получить список песен.")
                return
            song = random.choice(songs)
            title = song.get('title', 'Без названия')
            artist = song.get('artist', '')
            web_url = song.get('web_url', '')
            cover_url = song.get('cover_url', '')
            msg = f"🎲 Песня дня:\n<b>{title}</b> — {artist}\nhttps://www.smule.com{web_url}"
            print(f"Песня дня для {user_id}: {title} — {artist}")
            if cover_url:
                await context.bot.send_photo(chat_id, cover_url, caption=msg, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id, msg, parse_mode='HTML')
        except Exception as e:
            print(f"Ошибка при получении песни дня: {e}")
            await context.bot.send_message(chat_id, f"Ошибка при получении песни: {e}")
            
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
