#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команды развлечений: /random, /cat, /meme, /casino
"""

import asyncio
import time
import random
import requests
from telegram import Update
from telegram.ext import ContextTypes
from commands.common import build_binary_stream

# Словари для отслеживания времени последнего запроса по командам
last_russong_time = {}
last_cat_time = {}
last_meme_time = {}
last_casino_time = {}

def get_random_russian_song():
    """Получить случайную русскую песню с Last.fm"""
    try:
        # Используем предоставленный API ключ
        lastfm_api_key = "b25b959554ed76058ac220b7b2e0a026"

        # Используем метод tag.gettoptracks с тегом 'russian'
        url = f"http://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag=russian&api_key={lastfm_api_key}&format=json&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()

        if 'tracks' not in data or 'track' not in data['tracks']:
            print("Не удалось получить данные от Last.fm API (tag.getTopTracks/russian)")
            print(f"Ответ API: {data}")
            return None, None, None

        # Выбираем случайный трек из списка
        tracks = data['tracks']['track']
        if not tracks:
            return None, None, None

        track = random.choice(tracks)
        title = track['name']
        artist = track['artist']['name']
        # Получаем ссылку на трек
        track_url = track['url']

        return title, artist, track_url

    except Exception as e:
        print(f"Ошибка при получении песни с Last.fm (tag.getTopTracks/russian): {e}")
        return None, None, None


def fetch_cat_image():
    """Получить случайное изображение котика."""
    response = requests.get("https://cataas.com/cat", timeout=15)
    content_type = response.headers.get('Content-Type', '')
    return response.status_code, content_type, response.content


def fetch_memes():
    """Получить список мемов из Imgflip."""
    response = requests.get("https://api.imgflip.com/get_memes", timeout=10)
    response.raise_for_status()
    return response.json()

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /random"""
    # Ограничение по времени для команды /random
    user_id = update.effective_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов
    if user_id in last_russong_time and now - last_russong_time[user_id] < 5:
        remaining_time = int(5 - (now - last_russong_time[user_id]))
        await update.message.reply_text(f"⏳ Подождите {remaining_time} секунд перед следующим запросом.")
        return
    
    print(f"Команда /random от {update.effective_user.username or update.effective_user.id}")
    
    title, artist, link = await asyncio.to_thread(get_random_russian_song)
    if not title:
        await update.message.reply_text("😔 К сожалению, не удалось найти песню.")
        return
    
    # Обновляем время последнего запроса
    last_russong_time[user_id] = now
        
    response = (
        f"🎵 Случайная песня:\n\n"
        f"<b>{title}</b>\n"
        f"Исполнитель: {artist}\n\n"
        f"Ссылка на Last.fm:\n{link}"
    )
    await update.message.reply_text(response, parse_mode='HTML')

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cat"""
    # Ограничение по времени для команды /cat
    user_id = update.effective_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов для /cat
    if user_id in last_cat_time and now - last_cat_time[user_id] < 5:
        remaining_time = int(5 - (now - last_cat_time[user_id]))
        await update.message.reply_text(f"⏳ Подождите {remaining_time} секунд перед следующим запросом котика.")
        return
        
    print(f"Команда /cat от {update.effective_user.username or update.effective_user.id}")
    
    try:
        status_code, content_type, content = await asyncio.to_thread(fetch_cat_image)
        
        # Проверяем успешность запроса и тип контента (ожидаем изображение)
        if status_code == 200 and 'image' in content_type:
            await update.message.reply_photo(content, reply_to_message_id=update.message.message_id)
            print(f"Изображение котика отправлено в чат {update.message.chat.id} как ответ.")
            last_cat_time[user_id] = now # Обновляем время последнего запроса
        else:
            print(f"Не удалось получить изображение котика. Статус: {status_code}, Content-Type: {content_type}")
            await update.message.reply_text("😔 Не удалось получить изображение котика. Попробуйте позже.")
            
    except Exception as e:
        print(f"Ошибка при выполнении команды /cat: {e}")
        await update.message.reply_text(f"Произошла ошибка при получении котика: {e}")

async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /meme"""
    user_id = update.effective_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /meme
    if user_id in last_meme_time and now - last_meme_time[user_id] < 5:
        remaining_time = int(5 - (now - last_meme_time[user_id]))
        await update.message.reply_text(f"⏳ Подождите {remaining_time} секунд перед следующим запросом мема.")
        return

    print(f"Команда /meme от {update.effective_user.username or update.effective_user.id}")
    try:
        data = await asyncio.to_thread(fetch_memes)

        if data and data['success'] and data['data'] and data['data']['memes']:
            memes = data['data']['memes']
            random_meme = random.choice(memes)
            meme_url = random_meme['url']
            
            try:
                # Пробуем отправить как фото
                await update.message.reply_photo(meme_url, reply_to_message_id=update.message.message_id)
                print(f"Отправлен мем (Imgflip API): {meme_url}")
                last_meme_time[user_id] = now # Обновляем время последнего запроса
            except Exception as e:
                print(f"Не удалось отправить фото {meme_url} (Imgflip API): {e}")
                await update.message.reply_text(f'Вот случайный мем: {meme_url}')

        else:
            await update.message.reply_text('Не удалось получить список мемов от API.')
            print("Imgflip API не вернул список мемов")

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к Imgflip API: {e}")
        await update.message.reply_text('Не удалось подключиться к Imgflip API.')
    except Exception as e:
        print(f"Непредвиденная ошибка при обработке Imgflip API ответа: {e}")
        await update.message.reply_text('Произошла ошибка при обработке ответа от Imgflip API.')

async def casino_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /casino"""
    user_id = update.effective_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /casino
    if user_id in last_casino_time and now - last_casino_time[user_id] < 5:
        remaining_time = int(5 - (now - last_casino_time[user_id]))
        await update.message.reply_text(f"⏳ Подождите {remaining_time} секунд перед следующим запуском казино.")
        return

    print(f"Команда /casino от {update.effective_user.username or update.effective_user.id}")

    # Обновляем время последнего запроса
    last_casino_time[user_id] = now

    # Отправляем изображение казино как ответ на сообщение
    image_path = 'images/casino.png'
    photo = build_binary_stream(image_path)
    if photo:
        await update.message.reply_photo(photo, reply_to_message_id=update.message.message_id)
        print(f"Картинка {image_path} отправлена для команды /casino как ответ.")
    else:
        print(f"Файл картинки {image_path} не найден для команды /casino. Отправляю только символы.")

    # Список стандартных символов для слотов (теперь все эмодзи)
    symbols = [
        '🤞', # Эмодзи цифры 7
        '✌️' # Эмодзи Squared B (визуально похоже на BAR)
    ]

    # Генерируем 3 случайных символа
    result_symbols = [random.choice(symbols) for _ in range(3)]

    # Отправляем символы по очереди с задержкой как ответ на сообщение
    for symbol in result_symbols:
        try:
            await update.message.reply_text(symbol, reply_to_message_id=update.message.message_id)
            await asyncio.sleep(1) # Задержка в 1 секунду между символами
        except Exception as e:
            print(f"Ошибка при отправке символа казино {symbol}: {e}")

    # Проверяем выигрыш (все символы одинаковые)
    if all(x == result_symbols[0] for x in result_symbols):
        # Отправляем эмодзи при выигрыше (один символ)
        win_emoji = '🎉' # Эмодзи хлопушки
        try:
            await update.message.reply_text("ПОЗДРАВЛЯЕМ С ПОБЕДОЙ! 🎉", reply_to_message_id=update.message.message_id)
            await update.message.reply_text(win_emoji, reply_to_message_id=update.message.message_id)
        except Exception as e:
             print(f"Ошибка при отправке выигрышных эмодзи: {e}")
    else:
        # Отправляем эмодзи проигрыша при несовпадении символов (один символ)
        lose_emoji = '😢' # Эмодзи печального лица
        try:
            await update.message.reply_text("Повезет в следующий раз!", reply_to_message_id=update.message.message_id)
            await update.message.reply_text(lose_emoji, reply_to_message_id=update.message.message_id)
        except Exception as e:
             print(f"Ошибка при отправке проигрышных эмодзи: {e}")
