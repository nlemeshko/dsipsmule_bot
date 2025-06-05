import os
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from dotenv import load_dotenv
import time
import random
import requests
import csv
from datetime import datetime
import uuid
import asyncio
from PyCharacterAI import get_client
import traceback

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение токена бота и ID разрешенной группы из переменных окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ALLOWED_GROUP_ID = int(os.getenv('ALLOWED_GROUP_ID'))
CHARACTER_AI_TOKEN = os.getenv('CHARACTER_AI_TOKEN')
CHARACTER_ID = "0A-obi-Y3tezNqaOb5nvYXTkRmM39O9g1qkQKooP8RU"
CHARACTER_VOICE_ID = "25726345-4858-4c38-99a7-0d5fc583ff5e"

# Список админов для модерации (укажите user_id админов через запятую в .env)
ADMINS = os.getenv('ADMINS')
ADMIN_IDS = [int(uid) for uid in ADMINS.split(',') if uid.strip()]

# FSM: отслеживаем, кто сейчас пишет анонимку, предлагает песню, оценивает, или запрашивает промо
user_states = {}
ANON_STATE = 'anon_waiting_text'
SONG_STATE = 'song_waiting_text'
RATE_LINK_STATE = 'rate_waiting_link'
SONG_DAY_STATE = 'song_day_cooldown'
PROMOTE_STATE = 'promote_waiting_link'

# Словари для отслеживания времени последнего запроса по командам
last_song_day_time = {}
last_russong_time = {}
last_cat_time = {}
last_meme_time = {}
last_casino_time = {}
last_ask_time = {}

# Временное хранилище для запросов на промо перед модерацией
pending_promotions = {}

# Добавляем словарь для отслеживания состояния игры в "Поле чудес"
pole_games = {}

# Each game will store:
# 'word': the word to guess
# 'guessed_letters': set of letters guessed correctly
# 'used_letters': set of all letters used
# 'chat_id': the chat ID where the game is being played
# 'initial_message_id': the message_id of the initial game message sent by the bot
# 'bot_message_ids': list of bot's message IDs in the current game

# Список слов для игры в "Поле чудес"
pole_words = [
    "крыша", "окно", "дверь", "стена", "пол", "потолок", "лестница", "балкон",
    "подъезд", "лифт", "квартира", "дом", "дача", "гараж", "сарай", "баня",
    "бассейн", "спортзал", "кухня", "ванная", "спальня", "гостиная", "коридор",
    "кладовка", "чердак", "подвал", "фундамент", "крыльцо", "терраса", "веранда"
]

# Получение Client-ID Imgur из переменных окружения
IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')

# Функция для отправки случайного голосового сообщения
async def send_random_voice(bot, chat_id, folder, prefix, count):
    try:
        # Выбираем случайный номер
        number = random.randint(1, count)
        # Формируем путь к файлу
        voice_path = f"{folder}/{prefix}_{number}.mp3"
        
        if os.path.exists(voice_path):
            with open(voice_path, 'rb') as voice:
                await bot.send_voice(chat_id, voice)
            logging.info(f"Отправлено голосовое сообщение: {voice_path}")
        else:
            logging.error(f"Файл голосового сообщения не найден: {voice_path}")
    except Exception as e:
        logging.error(f"Ошибка при отправке голосового сообщения: {e}")

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

# Загрузка данных зала славы/позора
def load_hall_data():
    try:
        with open('hall.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except FileNotFoundError:
        return []

# Сохранение данных зала славы/позора
def save_hall_data(data):
    with open('hall.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['category', 'name', 'nominated_by', 'date', 'votes'])
        writer.writeheader()
        writer.writerows(data)

# Инициализация бота
bot = AsyncTeleBot(TOKEN)

@bot.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.chat.type not in ['private']:
        return
    logging.info(f"/start от {message.from_user.username or message.from_user.id} в чате {message.chat.id}")
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("1. 🕵 Анонимка", callback_data="button1"),
        types.InlineKeyboardButton("2. 🎶 Песня", callback_data="button2"),
        types.InlineKeyboardButton("3. 🎧 Оценить", callback_data="button3"),
        types.InlineKeyboardButton("4. 🎲 Песня дня", callback_data="button4"),
        types.InlineKeyboardButton("5. 📢 Промо", callback_data="button6")
    )
    await bot.reply_to(
        message,
        "Привет! Я ваш новый телеграм бот. Выберите действие:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
async def button_callback(call: types.CallbackQuery):
    if call.message.chat.type not in ['private']:
        return
    logging.info(f"Кнопка: {call.data} от {call.from_user.username or call.from_user.id} в чате {call.message.chat.id}")
    await bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "button1":
        user_states[user_id] = ANON_STATE
        logging.info(f"Установлено состояние ANON_STATE для пользователя {user_id}")
        response_text = "Отправьте текст, фотографию или голосовое сообщение для анонимки:"
        image_path = 'anon.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Анонимно.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Анонимно. Отправляю только текст.")
                await bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Анонимно: {e}")
            await bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button2":
        user_states[user_id] = SONG_STATE
        response_text = "Введи название песни или ссылку на неё. Можно добавить теги (например: #дуэт #челлендж #классика):"
        image_path = 'sing.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Предложить песню.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Предложить песню. Отправляю только текст.")
                await bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Предложить песню: {e}")
            await bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button3":
        user_states[user_id] = RATE_LINK_STATE
        response_text = "Отправь ссылку на свой трек в Smule:"
        image_path = 'rate.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Оценить исполнение.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Оценить исполнение. Отправляю только текст.")
                await bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Оценить исполнение: {e}")
            await bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button4":
        user_id = call.from_user.id
        now = time.time()
        if user_id in last_song_day_time and now - last_song_day_time[user_id] < 60:
            logging.info(f"Песня дня — лимит для {user_id}")
            await bot.send_message(call.message.chat.id, "Можно использовать не чаще 1 раза в минуту!")
            return
        last_song_day_time[user_id] = now
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
            }
            url = 'https://www.smule.com/api/profile/performances?accountId=96242367&appUid=sing&offset=0&limit=25'
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            songs = data.get('list', [])
            if not songs:
                logging.warning("Не удалось получить список песен с Smule API")
                await bot.send_message(call.message.chat.id, "Не удалось получить список песен.")
                return
            song = random.choice(songs)
            title = song.get('title', 'Без названия')
            artist = song.get('artist', '')
            web_url = song.get('web_url', '')
            cover_url = song.get('cover_url', '')
            msg = f"🎲 Песня дня:\n<b>{title}</b> — {artist}\nhttps://www.smule.com{web_url}"
            logging.info(f"Песня дня для {user_id}: {title} — {artist}")
            if cover_url:
                await bot.send_photo(call.message.chat.id, cover_url, caption=msg, parse_mode='HTML')
            else:
                await bot.send_message(call.message.chat.id, msg, parse_mode='HTML')
        except Exception as e:
            logging.error(f"Ошибка при получении песни дня: {e}")
            await bot.send_message(call.message.chat.id, f"Ошибка при получении песни: {e}")
    elif call.data == "button6":
        user_states[user_id] = PROMOTE_STATE
        response_text = "Отправьте ссылку на трек, который хотите пропиарить:"
        image_path = 'piar.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Пропиарь меня!.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Пропиарь меня!. Отправляю только текст.")
                await bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Пропиарь меня!: {e}")
            await bot.send_message(call.message.chat.id, response_text)

@bot.message_handler(commands=['meme'])
async def send_random_meme_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /meme
    if user_id in last_meme_time and now - last_meme_time[user_id] < 60:
        remaining_time = int(60 - (now - last_meme_time[user_id]))
        await bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом мема.")
        return

    logging.info(f"Команда /meme от {message.from_user.username or message.from_user.id}")
    meme_api_url = "https://api.imgflip.com/get_memes"
    try:
        response = requests.get(meme_api_url, timeout=10)
        response.raise_for_status() # Проверка на ошибки HTTP
        data = response.json()

        if data and data['success'] and data['data'] and data['data']['memes']:
            memes = data['data']['memes']
            random_meme = random.choice(memes)
            meme_url = random_meme['url']
            
            try:
                # Пробуем отправить как фото
                await bot.send_photo(message.chat.id, meme_url)
                logging.info(f"Отправлен мем (Imgflip API): {meme_url}")
                last_meme_time[user_id] = now # Обновляем время последнего запроса
            except Exception as e:
                logging.error(f"Не удалось отправить фото {meme_url} (Imgflip API): {e}")
                await bot.reply_to(message, f'Вот случайный мем: {meme_url}')

        else:
            await bot.reply_to(message, 'Не удалось получить список мемов от API.')
            logging.warning("Imgflip API не вернул список мемов")

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к Imgflip API: {e}")
        await bot.reply_to(message, 'Не удалось подключиться к Imgflip API.')
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при обработке Imgflip API ответа: {e}")
        await bot.reply_to(message, 'Произошла ошибка при обработке ответа от Imgflip API.')

@bot.message_handler(commands=['prediction'])
async def vocal_predictor(message: types.Message):
    logging.info(f"/prediction в чате {message.chat.id} от {message.from_user.username or message.from_user.id}")
    prediction = get_random_vocal_prediction()
    
    try:
        # Путь к файлу с картинкой
        image_path = 'prediction.png' # Укажите правильный путь, если файл не в той же директории

        # Проверяем, существует ли файл
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                # Отправляем картинку с текстом предсказания в подписи
                await bot.send_photo(message.chat.id, photo, caption=f"🧙‍♂️ Вокальный предсказатель:\n{prediction}")
            logging.info(f"Картинка {image_path} отправлена с предсказанием.")
        else:
            # Если файл не найден, отправляем только текст предсказания
            logging.warning(f"Файл картинки {image_path} не найден. Отправляю только текст.")
            await bot.reply_to(message, f"🧙‍♂️ Вокальный предсказатель:\n{prediction}")

    except Exception as e:
        logging.error(f"Ошибка при отправке картинки prediction.png или предсказания: {e}")
        await bot.reply_to(message, f"Произошла ошибка при получении предсказания: {e}")

@bot.message_handler(commands=['hall'])
async def hall_command(message: types.Message):
    logging.info(f"Команда /hall от {message.from_user.username or message.from_user.id}")
    
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await bot.reply_to(message, "Использование: /hall [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            await bot.reply_to(message, "Категория должна быть 'legend' или 'cringe'")
            return
        
        nominee = args[2]
        nominator = message.from_user.username or f"id{message.from_user.id}"
        
        # Проверяем, не номинирован ли уже этот пользователь
        hall_data = load_hall_data()
        for row in hall_data:
            if row['name'] == nominee and row['category'] == category:
                await bot.reply_to(message, f"@{nominee} уже номинирован в эту категорию!")
                return
        
        # Добавляем новую номинацию
        new_nomination = {
            "category": category,
            "name": nominee,
            "nominated_by": nominator,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "votes": '1' # Votes are stored as string in CSV DictReader/Writer
        }
        hall_data.append(new_nomination)
        save_hall_data(hall_data)
        
        category_emoji = "🏆" if category == "legend" else "🤦"
        response_text = (
            f"{category_emoji} Новая номинация!\n"
            f"Категория: {'Легенда' if category == 'legend' else 'Кринж'}\n"
            f"Номинант: {nominee}\n"
            f"Номинировал: {nominator}"
        )

        # Добавляем отправку картинки
        image_path = 'hall.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /hall.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /hall. Отправляю только текст.")
            await bot.reply_to(message, response_text)

        logging.info(f"Номинация создана: {response_text}")
        
    except Exception as e:
        logging.error(f"Ошибка в команде /hall: {e}")
        await bot.reply_to(message, f"Произошла ошибка при обработке команды: {e}")

@bot.message_handler(commands=['halllist'])
async def hall_list(message: types.Message):
    try:
        logging.info(f"Команда /halllist от {message.from_user.username or message.from_user.id}")
        
        hall_data = load_hall_data()
        
        legends = []
        cringe = []
        
        for row in hall_data:
            if row['category'] == 'legend':
                legends.append(row)
            else:
                cringe.append(row)
        
        legends_text = "🏆 Легенды:\n"
        for entry in legends:
            legends_text += f"• {entry['name']} (от {entry['nominated_by']}, {entry['votes']} голосов)\n"
        
        cringe_text = "\n🤦 Кринж:\n"
        for entry in cringe:
            cringe_text += f"• {entry['name']} (от {entry['nominated_by']}, {entry['votes']} голосов)\n"
        
        response_text = legends_text + cringe_text

        # Добавляем отправку картинки
        image_path = 'halllist.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /halllist.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /halllist. Отправляю только текст.")
            await bot.reply_to(message, response_text)
        
        logging.info(f"Список зала славы/позора отправлен: {response_text}")
        
    except Exception as e:
        logging.error(f"Ошибка в команде /halllist: {e}")
        await bot.reply_to(message, f"Произошла ошибка при получении списка: {e}")

@bot.message_handler(commands=['vote'])
async def vote_command(message: types.Message):
    logging.info(f"Команда /vote от {message.from_user.username or message.from_user.id}")
    
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await bot.reply_to(message, "Использование: /vote [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            await bot.reply_to(message, "Категория должна быть 'legend' или 'cringe'")
            return
        
        nominee = args[2]
        voter = message.from_user.username or f"id{message.from_user.id}"
        
        # Читаем текущие данные
        hall_data = load_hall_data()
        
        # Ищем номинацию
        found = False
        for row in hall_data:
            if row['name'] == nominee and row['category'] == category:
                row['votes'] = str(int(row['votes']) + 1) # Ensure votes remain string for CSV
                found = True
                break
        
        if not found:
            await bot.reply_to(message, f"Номинация для @{nominee} в категории {category} не найдена!")
            return
        
        # Сохраняем обновленные данные
        save_hall_data(hall_data)
        
        category_emoji = "🏆" if category == "legend" else "🤦"
        response_text = f"{category_emoji} Ваш голос за @{nominee} учтен!"

        # Добавляем отправку картинки
        image_path = 'vote.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /vote.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /vote. Отправляю только текст.")
            await bot.reply_to(message, response_text)

    except Exception as e:
        logging.error(f"Ошибка в команде /vote: {e}")
        await bot.reply_to(message, f"Произошла ошибка при голосовании: {e}")

def get_random_russian_song():
    try:
        # Используем предоставленный API ключ
        lastfm_api_key = "b25b959554ed76058ac220b7b2e0a026"

        # Используем метод tag.gettoptracks с тегом 'russian'
        url = f"http://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag=russian&api_key={lastfm_api_key}&format=json&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()

        if 'tracks' not in data or 'track' not in data['tracks']:
            logging.error("Не удалось получить данные от Last.fm API (tag.getTopTracks/russian)")
            logging.error(f"Ответ API: {data}")
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
        logging.error(f"Ошибка при получении песни с Last.fm (tag.getTopTracks/russian): {e}")
        return None, None, None

@bot.message_handler(commands=['random'])
async def russian_song_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов
    if user_id in last_russong_time and now - last_russong_time[user_id] < 60:
        remaining_time = int(60 - (now - last_russong_time[user_id]))
        await bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом.")
        return
    
    logging.info(f"Команда /random от {message.from_user.username or message.from_user.id}")
    
    title, artist, link = get_random_russian_song()
    if not title:
        await bot.reply_to(message, "😔 К сожалению, не удалось найти песню.")
        return
    
    # Обновляем время последнего запроса
    last_russong_time[user_id] = now
        
    response = (
        f"🎵 Случайная песня:\n\n"
        f"<b>{title}</b>\n"
        f"Исполнитель: {artist}\n\n"
        f"Ссылка на Last.fm:\n{link}"
    )
    await bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['cat'])
async def cat_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов для /cat
    if user_id in last_cat_time and now - last_cat_time[user_id] < 60:
        remaining_time = int(60 - (now - last_cat_time[user_id]))
        await bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом котика.")
        return
        
    logging.info(f"Команда /cat от {message.from_user.username or message.from_user.id}")
    
    try:
        # URL для получения случайного изображения котика с заданным размером
        cat_api_url = "http://theoldreader.com/kittens/600/400"
        
        response = requests.get(cat_api_url, timeout=10)
        
        # Проверяем успешность запроса и тип контента (ожидаем изображение)
        if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
            await bot.send_photo(message.chat.id, response.content)
            logging.info(f"Изображение котика отправлено в чат {message.chat.id}")
            last_cat_time[user_id] = now # Обновляем время последнего запроса
        else:
            logging.error(f"Не удалось получить изображение котика. Статус: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
            await bot.reply_to(message, "😔 Не удалось получить изображение котика. Попробуйте позже.")
            
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /cat: {e}")
        await bot.reply_to(message, f"Произошла ошибка при получении котика: {e}")

@bot.message_handler(commands=['casino'])
async def casino_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /casino
    if user_id in last_casino_time and now - last_casino_time[user_id] < 10:
        remaining_time = int(10 - (now - last_casino_time[user_id]))
        await bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запуском казино.")
        return

    logging.info(f"Команда /casino от {message.from_user.username or message.from_user.id}")

    # Обновляем время последнего запроса
    last_casino_time[user_id] = now

    # Отправляем изображение казино
    image_path = 'casino.png'
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await bot.send_photo(message.chat.id, photo)
        logging.info(f"Картинка {image_path} отправлена для команды /casino.")
    else:
        logging.warning(f"Файл картинки {image_path} не найден для команды /casino.")

    # Список стандартных символов для слотов (теперь все эмодзи)
    symbols = [
        '🤞', # Эмодзи цифры 7
        '✌️' # Эмодзи Squared B (визуально похоже на BAR)
    ]

    # Генерируем 3 случайных символа
    result_symbols = [random.choice(symbols) for _ in range(3)]

    # Отправляем символы по очереди с задержкой
    for symbol in result_symbols:
        try:
            await bot.send_message(message.chat.id, symbol)
            time.sleep(1) # Задержка в 1 секунду между символами
        except Exception as e:
            logging.error(f"Ошибка при отправке символа казино {symbol}: {e}")

    # Проверяем выигрыш (все символы одинаковые)
    if all(x == result_symbols[0] for x in result_symbols):
        # Отправляем эмодзи при выигрыше (один символ)
        win_emoji = '🎉' # Эмодзи хлопушки
        try:
            # bot.send_message(message.chat.id, win_emoji * 5) # Отправим несколько для наглядности
            await bot.send_message(message.chat.id, "ПОЗДРАВЛЯЕМ С ПОБЕДОЙ! 🎉")
            await bot.send_message(message.chat.id, win_emoji)
        except Exception as e:
             logging.error(f"Ошибка при отправке выигрышных эмодзи: {e}")
    else:
        # Отправляем эмодзи проигрыша при несовпадении символов (один символ)
        lose_emoji = '😢' # Эмодзи печального лица
        try:
            # bot.send_message(message.chat.id, lose_emoji * 3) # Отправим несколько
            await bot.send_message(message.chat.id, "Повезет в следующий раз!")
            await bot.send_message(message.chat.id, lose_emoji)
        except Exception as e:
             logging.error(f"Ошибка при отправке проигрышных эмодзи: {e}")

@bot.message_handler(commands=['help'])
async def help_command(message: types.Message):
    help_text = (
        "Список доступных команд:\n\n"
        "/prediction - Получить вокальное предсказание\n"
        "/hall [legend/cringe] [имя пользователя] - Номинировать пользователя в Зал славы/позора\n"
        "/halllist - Посмотреть списки Зала славы/позора\n"
        "/vote [legend/cringe] [имя пользователя] - Проголосовать за номинанта\n"
        "/random - Получить случайную русскую песню с Last.fm\n"
        "/cat - Получить случайное изображение котика\n"
        "/meme - Получить случайный мем\n"
        "/casino - Играть в слоты\n"
        "/pole - Играть в Поле чудес\n"
        "/ask [вопрос] - Задать вопрос AI-персонажу\n"
        "/help - Показать это сообщение помощи\n\n"
        "Также доступны функции через кнопки в главном меню (/start) в общении с @dsipsmule_bot:\n"
        "🕵 Анонимка\n"
        "🎶 Песня\n"
        "🎧 Оценить\n"
        "🎲 Песня дня\n"
        "📢 Промо"
    )
    
    # Добавляем отправку картинки
    image_path = 'help.png'
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await bot.send_photo(message.chat.id, photo, caption=help_text)
        logging.info(f"Картинка {image_path} отправлена для команды /help.")
    else:
        logging.warning(f"Файл картинки {image_path} не найден для команды /help. Отправляю только текст.")
        await bot.reply_to(message, help_text)

@bot.message_handler(commands=['pole'])
async def pole_command(message: types.Message):
    user_id = message.from_user.id
    
    # Если пользователь уже в игре "Поле чудес" в этом чате, считаем это попыткой угадать
    if user_id in pole_games and pole_games[user_id]['chat_id'] == message.chat.id:
        logging.info(f"Пользователь {user_id} уже в игре в чате {message.chat.id}. Обрабатываем как попытку угадать.")
        # Передаем сообщение на обработку в handle_message
        # Handle_message проверит, является ли это ответом на первое сообщение игры
        await handle_message(message)
        return

    logging.info(f"Начинаем новую игру Поле чудес для пользователя {user_id} в чате {message.chat.id}")
    # Создаем новую игру и сохраняем chat_id
    game_state = create_pole_game()
    game_state['chat_id'] = message.chat.id
    game_state['bot_message_ids'] = [] # Инициализируем список ID сообщений бота
    pole_games[user_id] = game_state
    game = pole_games[user_id]
    
    # Отправляем изображение поля чудес
    image_path = 'pole.png'
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await bot.send_photo(message.chat.id, photo)
        logging.info(f"Картинка {image_path} отправлена для команды /pole.")
    else:
        logging.warning(f"Файл картинки {image_path} не найден для команды /pole.")

    # Отправляем начальное состояние
    word_display = display_word(game['word'], game['guessed_letters'])
    letters_display = display_available_letters(game['used_letters'])

    response = (
        f"🎯 Игра 'Поле чудес' началась!\n\n"
        f"Слово: {word_display}\n\n"
        f"Доступные буквы:\n{letters_display}\n\n"
        f"Отправьте букву или попробуйте угадать слово целиком!"
    )

    # Отправляем сообщение в ответ на команду и сохраняем его message_id как initial_message_id
    initial_message = await bot.reply_to(message, response, parse_mode='HTML')
    pole_games[user_id]['bot_message_ids'].append(initial_message.message_id) # Добавляем ID первого сообщения
    pole_games[user_id]['initial_message_id'] = initial_message.message_id
    logging.info(f"Для пользователя {user_id} в чате {message.chat.id} сохранена initial_message_id: {initial_message.message_id}")

    # Отправляем случайное голосовое сообщение ожидания
    await send_random_voice(bot, message.chat.id, 'pole', 'wait', 3)

@bot.message_handler(content_types=['text', 'caption'])
async def handle_message(message: types.Message):
    # Логирование в самом начале функции для отладки получения всех сообщений
    logging.info(f"[handle_message start] Получено сообщение от {message.from_user.id}. Chat ID: {message.chat.id}. Content Type: {message.content_type}")
    
    user_id = message.from_user.id
    
    # Проверяем, играет ли пользователь в "Поле чудес"
    if user_id in pole_games:
        game = pole_games[user_id]
        
        # Проверяем, находится ли сообщение в том же чате, где началась игра
        if message.chat.id != game['chat_id']:
            logging.info(f"Сообщение от игрока {user_id} в другом чате ({message.chat.id}) во время игры в чате {game['chat_id']}. Игнорируем в контексте игры.")
            return # Игнорируем сообщение, если оно не из чата игры
        
        guess = None
        is_private_chat = message.chat.type == 'private'

        # --- Логика для личных чатов (цитирование не требуется) ---
        if is_private_chat:
            guess = message.text.lower().strip() if message.text else '' # Берем текст сообщения напрямую
            logging.info(f"Личный чат. Получено сообщение для Поле чудес: {guess}")

        # --- Логика для групповых чатов (цитирование обязательно) ---
        # Проверяем, является ли сообщение ответом на одно из сообщений бота в текущей игре
        elif message.reply_to_message and game.get('bot_message_ids') and message.reply_to_message.message_id in game['bot_message_ids']:
            guess = message.text.lower().strip() if message.text else '' # Берем текст из цитирующего сообщения
            logging.info(f"Групповой чат. Получена цитата для Поле чудес: {guess}")

        # Если guess был получен (либо из личного чата, либо из цитаты в группе)
        if guess is not None:
            # Если guess пустой после обрезки (например, пустая цитата или сообщение только с пробелами)
            if not guess:
                response = "Пожалуйста, введите букву или слово для угадывания." + (" в цитируемом сообщении." if not is_private_chat else "")
                await bot.reply_to(message, response)
                return # Выходим, не обрабатывая пустой ввод

            # Отправляем сообщение о том, что бот думает
            thinking_msg = await bot.reply_to(message, "🤔 Думаю...")
            game['bot_message_ids'].append(thinking_msg.message_id) # Добавляем ID сообщения "Думаю..."
            
            # Ждем 5 секунд
            time.sleep(5)
            
            # Если пользователь пытается угадать слово целиком
            if len(guess) > 1:
                if guess == game['word']:
                    response = (
                        f"🎉 Поздравляем! Вы угадали слово '{game['word']}'!\n"
                        f"Игра окончена. Чтобы начать новую игру, используйте команду /pole"
                    )
                    del pole_games[user_id]
                    # Отправляем голосовое сообщение победы
                    try:
                        with open('pole/win.mp3', 'rb') as voice:
                            await bot.send_voice(message.chat.id, voice)
                        logging.info("Отправлено голосовое сообщение победы: pole/win.mp3")
                    except Exception as e:
                        logging.error(f"Ошибка при отправке голосового сообщения победы: {e}")
                else:
                    response = "❌ Неверное слово! Продолжайте угадывать буквы." + (" Цитатой." if not is_private_chat else "")
                    # Отправляем случайное голосовое сообщение неверного ответа
                    # ID голосовых сообщений не добавляем в bot_message_ids, т.к. их не цитируют для хода
                    await send_random_voice(bot, message.chat.id, 'pole', 'no', 3)
            # Если пользователь пытается угадать букву
            elif len(guess) == 1 and guess.isalpha():
                if guess in game['used_letters']:
                    response = "Эта буква уже была использована!" + (" Цитатой." if not is_private_chat else "")
                    # Отправляем случайное голосовое сообщение неверного ответа
                    await send_random_voice(bot, message.chat.id, 'pole', 'no', 3)
                else:
                    game['used_letters'].add(guess)
                    if guess in game['word']:
                        game['guessed_letters'].add(guess)
                        response = "✅ Верно! Буква есть в слове." + (" Цитатой." if not is_private_chat else "")
                        # Отправляем случайное голосовое сообщение верного ответа
                        await send_random_voice(bot, message.chat.id, 'pole', 'yes', 3)
                    else:
                        response = "❌ Неверно! Такой буквы нет в слове." + (" Цитатой." if not is_private_chat else "")
                        # Отправляем случайное голосовое сообщение неверного ответа
                        await send_random_voice(bot, message.chat.id, 'pole', 'no', 3)
                    
                    # Проверяем, угадано ли всё слово
                    if all(letter in game['guessed_letters'] for letter in game['word']):
                        response = (
                            f"🎉 Поздравляем! Вы угадали слово '{game['word']}'!\n"
                            f"Игра окончена. Чтобы начать новую игру, используйте команду /pole"
                        )
                        del pole_games[user_id]
                        # Отправляем голосовое сообщение победы
                        try:
                            with open('pole/win.mp3', 'rb') as voice:
                                await bot.send_voice(message.chat.id, voice)
                            logging.info("Отправлено голосовое сообщение победы: pole/win.mp3")
                        except Exception as e:
                            logging.error(f"Ошибка при отправке голосового сообщения победы: {e}")
                    else:
                        # Показываем текущее состояние игры
                        word_display = display_word(game['word'], game['guessed_letters'])
                        letters_display = display_available_letters(game['used_letters'])
                        response += f"\n\nСлово: {word_display}\n\nДоступные буквы:\n{letters_display}"
            else:
                response = "Пожалуйста, отправьте одну букву или попробуйте угадать слово целиком." + (" Цитатой." if not is_private_chat else "")
                # Отправляем случайное голосовое сообщение неверного ответа
                # ID голосовых сообщений не добавляем в bot_message_ids, т.к. их не цитируют для хода
                await send_random_voice(bot, message.chat.id, 'pole', 'no', 3)
            
            # Удаляем сообщение "Думаю..."
            await bot.delete_message(message.chat.id, thinking_msg.message_id)
            
            # Отправляем ответ
            response_message = await bot.reply_to(message, response, parse_mode='HTML')
            game['bot_message_ids'].append(response_message.message_id) # Добавляем ID ответного сообщения
            return

        # Если это не цитата одного из сообщений бота в игре, игнорируем
        logging.info("Сообщение не является цитатой одного из сообщений бота в игре. Игнорируем в контексте игры.")
        return

    # Добавляем логирование для отладки
    logging.info(f"Получено сообщение от {user_id}. Тип: {message.content_type}")
    logging.info(f"Текущее состояние пользователя: {user_states.get(user_id)}")
    
    # Добавляем логирование текста сообщения и эмодзи
    if message.text:
        logging.info(f"Текст сообщения: {message.text}")
        # Проверяем наличие эмодзи в тексте
        emoji_list = [char for char in message.text if ord(char) > 127]
        if emoji_list:
            logging.info(f"Найдены эмодзи в сообщении: {emoji_list}")

    # Список известных команд
    known_commands = [
        '/start', '/prediction', '/hall', '/halllist', '/vote',
        '/random', '/cat', '/meme', '/help', '/casino', '/pole', '/ask'
    ]

    # Если сообщение является известной командой, позволяем обработчику команды выполнить свою логику
    if message.text and message.text.split()[0].lower() in known_commands:
        logging.info(f"Сообщение является известной командой: {message.text.split()[0].lower()}. Позволяем обработчику команды работать.")
        return # Выходим из handle_message, чтобы обработчик команды мог работать

    # FSM: если пользователь пишет анонимку
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"Пользователь {user_id} в ANON_STATE. Проверка типа сообщения.")
        if message.text:
            # Обработка текстовых сообщений
            text = message.text.strip()
            anon_text = f"{text}\n\n#анон"
            for admin_id in ADMIN_IDS:
                await bot.send_message(admin_id, f"Новая анонимка на модерацию:\n\n{anon_text}\n\n")
            logging.info(f"Анонимка от {user_id} отправлена на модерацию")
            await bot.reply_to(message, "Спасибо! Ваша анонимка отправлена на модерацию.")
            user_states.pop(user_id, None)
            return

    # FSM: если пользователь предлагает песню
    elif user_states.get(user_id) == SONG_STATE:
        logging.info(f"Пользователь {user_id} в SONG_STATE. Обработка сообщения.")
        song_info = message.text.strip()
        if song_info:
            user_info = message.from_user.username or f"id{user_id}"
            message_to_admin = f"Новая песня предложена от @{user_info}:\n{song_info}"
            for admin_id in ADMIN_IDS:
                await bot.send_message(admin_id, message_to_admin)
            logging.info(f"Песня от {user_id} отправлена админам: {song_info}")
            await bot.reply_to(message, "Спасибо! Ваша песня отправлена администраторам.")
            user_states.pop(user_id, None)
            return
        else:
            await bot.reply_to(message, "Пожалуйста, отправьте название или ссылку на песню.")
            return
            
    # FSM: если пользователь отправляет ссылку для оценки
    elif user_states.get(user_id) == RATE_LINK_STATE:
        logging.info(f"Пользователь {user_id} в RATE_LINK_STATE. Обработка сообщения.")
        rate_link = message.text.strip()
        if rate_link:
            user_info = message.from_user.username or f"id{user_id}"
            message_to_admin = f"Новая ссылка для оценки от @{user_info}:\n{rate_link}"
            for admin_id in ADMIN_IDS:
                await bot.send_message(admin_id, message_to_admin)
            logging.info(f"Ссылка для оценки от {user_id} отправлена админам: {rate_link}")
            await bot.reply_to(message, "Спасибо! Ваша ссылка отправлена администраторам для оценки.")
            user_states.pop(user_id, None)
            return
        else:
            await bot.reply_to(message, "Пожалуйста, отправьте ссылку на трек для оценки.")
            return
            
    # FSM: если пользователь отправляет ссылку для промо
    elif user_states.get(user_id) == PROMOTE_STATE:
        logging.info(f"Пользователь {user_id} в PROMOTE_STATE. Обработка сообщения.")
        promote_link = message.text.strip()
        if promote_link:
            user_info = message.from_user.username or f"id{user_id}"
            # Сохраняем промо запрос перед модерацией
            promotion_id = str(uuid.uuid4()) # Генерируем уникальный ID
            pending_promotions[promotion_id] = {
                'user_id': user_id,
                'username': user_info,
                'link': promote_link,
                'timestamp': datetime.now().isoformat()
            }
            
            # Формируем сообщение для админов с кнопками модерации
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_promo_{promotion_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_promo_{promotion_id}")
            )
            message_to_admin = f"Новый запрос на промо от @{user_info}:\n{promote_link}"
            for admin_id in ADMIN_IDS:
                await bot.send_message(admin_id, message_to_admin, reply_markup=keyboard)
                
            logging.info(f"Промо запрос от {user_id} отправлен админам на модерацию: {promote_link}")
            await bot.reply_to(message, "Спасибо! Ваш запрос на промо отправлен на модерацию.")
            user_states.pop(user_id, None)
            return
        else:
            await bot.reply_to(message, "Пожалуйста, отправьте ссылку на трек для промо.")
            return

@bot.message_handler(content_types=['photo'])
async def handle_anon_photo(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"[handle_anon_photo] Получена фотография от {user_id} в ANON_STATE.")
        # Обработка фотографий
        photo_id = message.photo[-1].file_id  # Берем последнюю (самую большую) версию фото
        caption = message.caption or ""
        anon_text = f"{caption}\n\n#анон" if caption else "#анон"
        try:
            for admin_id in ADMIN_IDS:
                await bot.send_photo(admin_id, photo_id, caption=anon_text)
            logging.info(f"Анонимная фотография от {user_id} успешно отправлена на модерацию")
            await bot.reply_to(message, "Спасибо! Ваша анонимная фотография отправлена на модерацию.")
        except Exception as e:
            logging.error(f"[handle_anon_photo] Ошибка при отправке фото админам: {e}")
            await bot.reply_to(message, "Произошла ошибка при отправке фотографии. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

@bot.message_handler(content_types=['voice'])
async def handle_anon_voice(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"[handle_anon_voice] Получено голосовое сообщение от {user_id} в ANON_STATE.")
        # Обработка голосовых сообщений
        voice_id = message.voice.file_id
        caption = message.caption or ""
        anon_text = f"{caption}\n\n#анон" if caption else "#анон"
        try:
            for admin_id in ADMIN_IDS:
                await bot.send_voice(admin_id, voice_id, caption=anon_text)
            logging.info(f"Анонимное голосовое сообщение от {user_id} успешно отправлено на модерацию")
            await bot.reply_to(message, "Спасибо! Ваше анонимное голосовое сообщение отправлено на модерацию.")
        except Exception as e:
            logging.error(f"[handle_anon_voice] Ошибка при отправке голосового сообщения админам: {e}")
            await bot.reply_to(message, "Произошла ошибка при отправке голосового сообщения. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

@bot.message_handler(content_types=['dice'])
async def handle_dice(message: types.Message):
    # Удаляем этот обработчик, так как фокусируемся на использовании file_id в команде /casino
    pass # Placeholder for removal

@bot.message_handler(content_types=['sticker'])
async def handle_sticker(message: types.Message):
    # Удаляем этот обработчик
    pass # Placeholder for removal

def get_random_vocal_prediction():
    try:
        with open('vocal.csv', encoding='utf-8') as f:
            reader = list(csv.reader(f))
            if not reader:
                return "🔮 Не удалось получить предсказание."
            row = random.choice(reader)
            return row[0] if row else "🔮 Не удалось получить предсказание."
    except Exception as e:
        logging.error(f"Ошибка чтения vocal.csv: {e}")
        return "🔮 Не удалось получить предсказание."

@bot.message_handler(commands=['ask'])
async def ask_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /ask (10 секунд)
    if user_id in last_ask_time and now - last_ask_time[user_id] < 10:
        remaining_time = int(10 - (now - last_ask_time[user_id]))
        await bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим вопросом.")
        return

    # Обновляем время последнего запроса
    last_ask_time[user_id] = now

    # Проверяем, есть ли текст после команды
    if not message.text or len(message.text.split()) < 2:
        await bot.reply_to(message, "Пожалуйста, напишите ваш вопрос после команды /ask")
        return

    # Извлекаем вопрос из сообщения
    question = ' '.join(message.text.split()[1:])
    logging.info(f"Получен вопрос для CharacterAI: {question}")

    # Отправляем сообщение о том, что бот думает
    thinking_msg = await bot.reply_to(message, "Думаю...")

    client = None # Инициализируем client перед try
    try:
        logging.info("Начинаем подключение к CharacterAI...")
        client = await get_client(token=CHARACTER_AI_TOKEN)
        logging.info("Клиент CharacterAI создан")

        try:
            logging.info(f"Создаем чат с персонажем ID: {CHARACTER_ID}")
            # Метод create_chat возвращает кортеж: (Chat object, Turn object)
            chat_response_tuple = await client.chat.create_chat(CHARACTER_ID)
            chat_object = chat_response_tuple[0]

            logging.info("Отправляем сообщение в чат...")
            # Вызываем send_message на client.chat и передаем необходимые аргументы
            response = await client.chat.send_message(CHARACTER_ID, chat_object.chat.id, question)
            reply = response.get_primary_candidate().text
            logging.info(f"CharacterAI: Получен ответ: {reply}")

            logging.info(f"Генерируем голосовой ответ для chat_id: {response.chat.id}, turn_id: {response.turn_id}, primary_candidate_id: {response.primary_candidate_id}, voice_id: {CHARACTER_VOICE_ID}")
            # Используем переменную client, созданную выше
            speech = await client.utils.generate_speech(response.chat.id, response.turn_id, response.primary_candidate_id, CHARACTER_VOICE_ID)
            logging.info("Голосовой ответ сгенерирован.")

            # Отправляем голосовое сообщение пользователю
            logging.info("Отправляем голосовое сообщение пользователю...")
            await bot.send_voice(message.chat.id, speech)
            logging.info("Голосовое сообщение отправлено.")

            # Отправляем изображение ask.png
            image_path = 'ask.png'
            if os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        await bot.send_photo(message.chat.id, photo)
                    logging.info(f"Картинка {image_path} отправлена для команды /ask.")
                except Exception as e:
                    logging.error(f"Ошибка при отправке картинки {image_path} для команды /ask: {e}")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для команды /ask.")

        except Exception as e:
            logging.error(f"Ошибка при работе с CharacterAI: {str(e)}")
            logging.error(f"Traceback: {traceback.format_exc()}")
            # Попробуем удалить "Думаю...", если оно еще не удалено
            try:
                await bot.delete_message(message.chat.id, thinking_msg.message_id)
            except Exception:
                pass # Игнорируем ошибку, если сообщение уже удалено или не существует
            await bot.reply_to(message, f"Произошла ошибка при получении ответа от CharacterAI: {str(e)}")
        finally:
            # Закрываем сессию клиента, если он был успешно создан
            if client:
                logging.info("Закрываем сессию CharacterAI")
                await client.close_session()

    except Exception as e:
        logging.error(f"Ошибка при создании клиента CharacterAI: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        await bot.delete_message(message.chat.id, thinking_msg.message_id)
        await bot.reply_to(message, f"Произошла ошибка при подключении к CharacterAI: {str(e)}")

def main():
    """Основная функция запуска бота"""
    if not ALLOWED_GROUP_ID:
        logging.error("ALLOWED_GROUP_ID не установлен в .env файле!")
        return

    # Запускаем бота
    asyncio.run(bot.polling(non_stop=True))

if __name__ == '__main__':
    main() 