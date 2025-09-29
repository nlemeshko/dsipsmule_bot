#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда /ask - AI-персонаж с голосовыми ответами
"""

import os
import time
import traceback
from telegram import Update
from telegram.ext import ContextTypes

# Условный импорт CharacterAI
try:
    from PyCharacterAI import get_client
    CHARACTER_AI_AVAILABLE = True
except ImportError:
    CHARACTER_AI_AVAILABLE = False
    print("Предупреждение: PyCharacterAI не установлен. Команда /ask будет работать в упрощенном режиме.")

# Словарь для отслеживания времени последнего запроса
last_ask_time = {}

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /ask"""
    user_id = update.effective_user.id
    now = time.time()

    print(f"[ask_command start] Вызвана команда /ask пользователем {user_id} в чате {update.message.chat.id}")

    # Проверяем ограничение на частоту запросов для /ask (5 секунд)
    if user_id in last_ask_time and now - last_ask_time[user_id] < 5:
        remaining_time = int(5 - (now - last_ask_time[user_id]))
        await update.message.reply_text(f"⏳ Подождите {remaining_time} секунд перед следующим вопросом.")
        return

    # Обновляем время последнего запроса
    last_ask_time[user_id] = now

    # Проверяем, есть ли текст после команды
    if not update.message.text or len(update.message.text.split()) < 2:
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос после команды /ask")
        return

    # Извлекаем вопрос из сообщения
    question = ' '.join(update.message.text.split()[1:])
    print(f"Получен вопрос: {question}")

    # Проверяем доступность CharacterAI
    if not CHARACTER_AI_AVAILABLE:
        await update.message.reply_text("❌ CharacterAI недоступен. Установите PyCharacterAI: pip install PyCharacterAI")
        return

    # Проверяем настройки окружения
    character_ai_token = os.getenv('CHARACTER_AI_TOKEN')
    character_id = os.getenv('CHARACTER_ID')
    character_voice_id = os.getenv('CHARACTER_VOICE_ID')
    
    if not all([character_ai_token, character_id, character_voice_id]):
        await update.message.reply_text("❌ CharacterAI не настроен. Проверьте переменные окружения: CHARACTER_AI_TOKEN, CHARACTER_ID, CHARACTER_VOICE_ID")
        return

    # Отправляем сообщение о том, что бот думает, как ответ
    thinking_msg = await update.message.reply_text("Думаю...")

    client = None # Инициализируем client перед try
    try:
        print("Начинаем подключение к CharacterAI...")
        # Создание клиента CharacterAI
        client = await get_client(token=os.getenv('CHARACTER_AI_TOKEN'))
        print("Клиент CharacterAI создан успешно.")

        try:
            print(f"Создаем чат с персонажем ID: {os.getenv('CHARACTER_ID')}...")
            # Метод create_chat возвращает кортеж: (Chat object, Turn object)
            # Первый элемент кортежа - это Chat object
            chat_response_tuple = await client.chat.create_chat(os.getenv('CHARACTER_ID'))
            chat_object = chat_response_tuple[0] # This is a Chat object
            
            # Получаем ID чата из Chat object
            chat_id_cai = chat_object.chat_id 
            
            print(f"Чат с персонажем {os.getenv('CHARACTER_ID')} создан. Chat ID: {chat_id_cai}")

            print(f"Отправляем сообщение в чат {chat_id_cai} с вопросом: {question}...")
            # Вызываем send_message на client.chat и передаем необходимые аргументы
            # Этот вызов возвращает Turn object
            question_full = "Тебя в чате спрашивают " + question
            response_cai = await client.chat.send_message(os.getenv('CHARACTER_ID'), chat_id_cai, question_full)
            print(f"Сообщение отправлено. Получен ответ от CharacterAI.")
            
            # turn_id и primary_candidate_id получаем напрямую из объекта Turn (response)
            turn_id = response_cai.turn_id
            primary_candidate_id = response_cai.primary_candidate_id
            reply_text_cai = response_cai.get_primary_candidate().text
            print(f"CharacterAI: Получен текстовый ответ: {reply_text_cai}")

            print(f"Генерируем голосовой ответ для chat_id: {chat_id_cai}, turn_id: {turn_id}, primary_candidate_id: {primary_candidate_id}, voice_id: {os.getenv('CHARACTER_VOICE_ID')}...")
            # Используем переменную client, созданную выше, и корректные ID
            speech = await client.utils.generate_speech(chat_id_cai, turn_id, primary_candidate_id, os.getenv('CHARACTER_VOICE_ID'))
            print("Голосовой ответ сгенерирован успешно.")

            # Отправляем голосовое сообщение пользователю как ответ
            print("Отправляем голосовое сообщение пользователю...")
            await context.bot.send_voice(update.message.chat.id, speech, reply_to_message_id=update.message.message_id)
            print("Голосовое сообщение отправлено успешно.")

            # Отправляем изображение ask.png как ответ
            image_path = 'images/ask.png'
            if os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        await context.bot.send_photo(update.message.chat.id, photo, reply_to_message_id=update.message.message_id)
                    print(f"Картинка {image_path} отправлена для команды /ask как ответ.")
                except Exception as e:
                    print(f"Ошибка при отправке картинки {image_path} для команды /ask: {e}")
            else:
                print(f"Файл картинки {image_path} не найден для команды /ask. Отправляю только голосовой ответ.")

        except Exception as inner_e:
            print(f"[CharacterAI Interaction Error] Ошибка при работе с CharacterAI: {str(inner_e)}")
            print(f"Traceback: {traceback.format_exc()}")
            # Попробуем удалить "Думаю...", если оно еще не удалено
            try:
                await context.bot.delete_message(update.message.chat.id, thinking_msg.message_id)
            except Exception:
                pass # Игнорируем ошибку, если сообщение уже удалено или не существует
            await update.message.reply_text(f"Произошла ошибка при получении ответа от CharacterAI: {str(inner_e)}")
        finally:
            # Закрываем сессию клиента, если он был успешно создан
            if client:
                print("Закрываем сессию CharacterAI")
                await client.close_session()

    except Exception as e:
        print(f"[CharacterAI Client Error] Ошибка при создании клиента CharacterAI: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        await context.bot.delete_message(update.message.chat.id, thinking_msg.message_id)
        await update.message.reply_text(f"Произошла ошибка при подключении к CharacterAI: {str(e)}")