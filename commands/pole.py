#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Игра "Поле чудес" - команда /pole
"""

import random
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from commands.common import build_binary_stream

# Список слов для игры в "Поле чудес"
pole_words = [
    "крыша", "окно", "дверь", "стена", "пол", "потолок", "лестница", "балкон",
    "подъезд", "лифт", "квартира", "дом", "дача", "гараж", "сарай", "баня",
    "бассейн", "спортзал", "кухня", "ванная", "спальня", "гостиная", "коридор",
    "кладовка", "чердак", "подвал", "фундамент", "крыльцо", "терраса", "веранда",
    "ананас", "банан", "виноград", "груша", "дыня", "ежевика", "жасмин", "земляника", "имбирь", "йогурт",
    "киви", "лимон", "манго", "нектарин", "огурец", "перец", "редис", "слива", "тыква", "укроп",
    "фенхель", "хурма", "цукини", "черешня", "шпинат", "щавель", "эстрагон", "юкка", "яблоко", "абрикос",
    "баклажан", "ваниль", "гранат", "дуриан", "ежевика", "женьшень", "зеленый", "ирга", "йогурт", "кокос",
    "лайм", "мандарин", "нут", "оливка", "петрушка", "ревень", "сельдерей", "тимьян", "устрица", "финик",
    "хрен", "цикорий", "чеснок", "шалфей", "щавель", "эхинацея", "юкка", "ягода", "айва", "брокколи",
    "васаби", "грейпфрут", "дыня", "ежевика", "жасмин", "земляника", "имбирь", "йогурт", "киви", "лимон",
    "манго", "нектарин", "огурец", "перец", "редис", "слива", "тыква", "укроп", "фенхель", "хурма",
    "цукини", "черешня", "шпинат", "щавель", "эстрагон", "юкка", "яблоко", "абрикос", "баклажан", "ваниль",
    "гранат", "дуриан", "ежевика", "женьшень", "зеленый", "ирга", "йогурт", "кокос", "лайм", "мандарин",
    "нут", "оливка", "петрушка", "ревень", "сельдерей", "тимьян", "устрица", "финик", "хрен", "цикорий",
    "чеснок", "шалфей", "щавель", "эхинацея", "юкка", "ягода", "айва", "брокколи", "васаби", "грейпфрут"
]

# Глобальный словарь для отслеживания состояния игры
pole_games = {}

# Функция для отправки случайного голосового сообщения
async def send_random_voice(bot, chat_id, folder, prefix, count):
    try:
        # Выбираем случайный номер
        number = random.randint(1, count)
        # Формируем путь к файлу
        voice_path = f"{folder}/{prefix}_{number}.mp3"

        voice = build_binary_stream(voice_path)
        if voice:
            await bot.send_voice(chat_id, voice)
            print(f"Отправлено голосовое сообщение: {voice_path}")
        else:
            print(f"Файл голосового сообщения не найден: {voice_path}")
    except Exception as e:
        print(f"Ошибка при отправке голосового сообщения: {e}")

# Функция для создания начального состояния игры
def create_pole_game():
    word = random.choice(pole_words)
    guessed_letters = set()
    used_letters = set()
    return {
        'word': word,
        'guessed_letters': guessed_letters,
        'used_letters': used_letters
    }

# Функция для отображения текущего состояния слова
def display_word(word, guessed_letters):
    return ' '.join(letter if letter in guessed_letters else '_' for letter in word)

# Функция для отображения доступных букв
def display_available_letters(used_letters):
    alphabet = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    return ' '.join(letter if letter not in used_letters else '~~' + letter + '~~' for letter in alphabet)

async def pole_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /pole"""
    msg = update.effective_message
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    print(f"🔍 POLE COMMAND DEBUG: /pole запущен пользователем {user_id} в чате {chat_id}, тип чата: {chat_type}")
    
    # Если пользователь уже в игре "Поле чудес" в этом чате, считаем это попыткой угадать
    if user_id in pole_games and pole_games[user_id]['chat_id'] == chat_id:
        print(f"Пользователь {user_id} уже в игре в чате {chat_id}. Обрабатываем как попытку угадать.")
        # Передаем сообщение на обработку в handle_pole_message
        await handle_pole_message(update, context)
        return

    print(f"Начинаем новую игру Поле чудес для пользователя {user_id} в чате {chat_id}")
    # Создаем новую игру и сохраняем chat_id
    game_state = create_pole_game()
    game_state['chat_id'] = chat_id
    game_state['bot_message_ids'] = [] # Инициализируем список ID сообщений бота
    pole_games[user_id] = game_state
    # Debug removed
    game = pole_games[user_id]
    
    # Отправляем изображение поля чудес как ответ на сообщение
    image_path = 'images/pole.png'
    photo = build_binary_stream(image_path)
    if photo:
        if msg:
            await msg.reply_photo(photo, reply_to_message_id=msg.message_id)
        print(f"Картинка {image_path} отправлена для команды /pole как ответ.")
    else:
        print(f"Файл картинки {image_path} не найден для команды /pole. Отправляю только текст.")

    # Отправляем начальное состояние как ответ на сообщение
    word_display = display_word(game['word'], game['guessed_letters'])
    letters_display = display_available_letters(game['used_letters'])

    response = (
        f"🎯 Игра 'Поле чудес' началась!\n\n"
        f"Слово: {word_display}\n\n"
        f"Доступные буквы:\n{letters_display}\n\n"
        f"Отправьте букву или попробуйте угадать слово целиком!"
    )

    # Отправляем сообщение в ответ на команду и сохраняем его message_id как initial_message_id
    initial_message = await msg.reply_text(response, parse_mode='HTML') if msg else None
    if initial_message:
        pole_games[user_id]['bot_message_ids'].append(initial_message.message_id) # Добавляем ID первого сообщения
        pole_games[user_id]['initial_message_id'] = initial_message.message_id
        print(f"Для пользователя {user_id} в чате {chat_id} сохранена initial_message_id: {initial_message.message_id}")

    # Отправляем случайное голосовое сообщение ожидания
    await send_random_voice(context.bot, chat_id, 'pole', 'wait', 3)

async def handle_pole_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений в игре Поле чудес"""
    user_id = update.effective_user.id
    msg = update.effective_message
    chat = update.effective_chat
    if not chat or not msg:
        return
    chat_id = chat.id
    
    # Debug removed
    
    # Ищем активную игру в этом чате
    active_game = None
    game_owner = None
    
    for owner_id, game in pole_games.items():
        if game['chat_id'] == chat_id:
            active_game = game
            game_owner = owner_id
            break
    
    if not active_game:
        return # Нет активной игры в этом чате
    
    game = active_game

    guess = msg.text.lower().strip() if (msg and msg.text) else ''
    print(f"Обрабатываем как ход в Поле чудес. Угадывание: {guess}")

    # Если guess пустой после обрезки
    if not guess:
        response = "Пожалуйста, введите букву или слово для угадывания."
        await msg.reply_text(response)
        return # Выходим, не обрабатывая пустой ввод

    # Отправляем сообщение о том, что бот думает
    thinking_msg = await msg.reply_text("🤔 Думаю...")
    game['bot_message_ids'].append(thinking_msg.message_id) # Добавляем ID сообщения "Думаю..."
    
    # Добавляем небольшую задержку для имитации "раздумий"
    await asyncio.sleep(1)
    
    # Если пользователь пытается угадать слово целиком
    if len(guess) > 1:
        if guess == game['word']:
            response = (
                f"🎉 Поздравляем! Вы угадали слово '{game['word']}'!\n"
                f"Игра окончена. Чтобы начать новую игру, используйте команду /pole"
            )
            del pole_games[game_owner]
            # Отправляем голосовое сообщение победы как ответ на сообщение
            try:
                voice = build_binary_stream('pole/win.mp3')
                if voice:
                    await context.bot.send_voice(chat_id, voice, reply_to_message_id=msg.message_id)
                    print("Отправлено голосовое сообщение победы: pole/win.mp3")
            except Exception as e:
                print(f"Ошибка при отправке голосового сообщения победы: {e}")
        else:
            response = "❌ Неверное слово! Продолжайте угадывать буквы."
            # Отправляем случайное голосовое сообщение неверного ответа
            await send_random_voice(context.bot, chat_id, 'pole', 'no', 3)
    # Если пользователь пытается угадать букву
    elif len(guess) == 1 and guess.isalpha():
        if guess in game['used_letters']:
            response = "Эта буква уже была использована!"
            # Отправляем случайное голосовое сообщение неверного ответа
            await send_random_voice(context.bot, chat_id, 'pole', 'no', 3)
        else:
            game['used_letters'].add(guess)
            if guess in game['word']:
                game['guessed_letters'].add(guess)
                response = "✅ Верно! Буква есть в слове."
                # Отправляем случайное голосовое сообщение верного ответа
                await send_random_voice(context.bot, chat_id, 'pole', 'yes', 3)
            else:
                response = "❌ Неверно! Такой буквы нет в слове."
                # Отправляем случайное голосовое сообщение неверного ответа
                await send_random_voice(context.bot, chat_id, 'pole', 'no', 3)
            
            # Проверяем, угадано ли всё слово
            if all(letter in game['guessed_letters'] for letter in game['word']):
                response = (
                    f"🎉 Поздравляем! Вы угадали слово '{game['word']}'!\n"
                    f"Игра окончена. Чтобы начать новую игру, используйте команду /pole"
                )
                del pole_games[game_owner]
                # Отправляем голосовое сообщение победы как ответ на сообщение
                try:
                    voice = build_binary_stream('pole/win.mp3')
                    if voice:
                        await context.bot.send_voice(chat_id, voice, reply_to_message_id=msg.message_id)
                        print("Отправлено голосовое сообщение победы: pole/win.mp3")
                except Exception as e:
                    print(f"Ошибка при отправке голосового сообщения победы: {e}")
            else:
                # Показываем текущее состояние игры
                word_display = display_word(game['word'], game['guessed_letters'])
                letters_display = display_available_letters(game['used_letters'])
                response += f"\n\nСлово: {word_display}\n\nДоступные буквы:\n{letters_display}"
    else:
        response = "Пожалуйста, отправьте одну букву или попробуйте угадать слово целиком."
        # Отправляем случайное голосовое сообщение неверного ответа
        await send_random_voice(context.bot, chat_id, 'pole', 'no', 3)
    
    # Удаляем сообщение "Думаю..."
    await context.bot.delete_message(chat_id, thinking_msg.message_id)
    
    # Отправляем ответ
    response_message = await msg.reply_text(response, parse_mode='HTML')
    game['bot_message_ids'].append(response_message.message_id) # Добавляем ID ответного сообщения
