import os
import logging
import telebot
from telebot import types
from dotenv import load_dotenv
import time
import random
import requests
import csv
import json
from datetime import datetime
import uuid

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
last_song_day_time = {}

# Временное хранилище для запросов на промо перед модерацией
pending_promotions = {}

# Добавляем словарь для отслеживания времени последнего запроса
last_russong_time = {}

# Получение Client-ID Imgur из переменных окружения
IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')

# Добавляем словари для отслеживания времени последнего запроса для /cat и /meme
last_cat_time = {}
last_meme_time = {}

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
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message: types.Message):
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
    bot.reply_to(
        message,
        "Привет! Я ваш новый телеграм бот. Выберите действие:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
def button_callback(call: types.CallbackQuery):
    if call.message.chat.type not in ['private']:
        return
    logging.info(f"Кнопка: {call.data} от {call.from_user.username or call.from_user.id} в чате {call.message.chat.id}")
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "button1":
        user_states[user_id] = ANON_STATE
        logging.info(f"Установлено состояние ANON_STATE для пользователя {user_id}")
        response_text = "Отправьте текст, фотографию или голосовое сообщение для анонимки:"
        image_path = 'anon.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Анонимно.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Анонимно. Отправляю только текст.")
                bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Анонимно: {e}")
            bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button2":
        user_states[user_id] = SONG_STATE
        response_text = "Введи название песни или ссылку на неё. Можно добавить теги (например: #дуэт #челлендж #классика):"
        image_path = 'sing.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Предложить песню.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Предложить песню. Отправляю только текст.")
                bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Предложить песню: {e}")
            bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button3":
        user_states[user_id] = RATE_LINK_STATE
        response_text = "Отправь ссылку на свой трек в Smule:"
        image_path = 'rate.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Оценить исполнение.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Оценить исполнение. Отправляю только текст.")
                bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Оценить исполнение: {e}")
            bot.send_message(call.message.chat.id, response_text)
    elif call.data == "button4":
        user_id = call.from_user.id
        now = time.time()
        if user_id in last_song_day_time and now - last_song_day_time[user_id] < 60:
            logging.info(f"Песня дня — лимит для {user_id}")
            bot.send_message(call.message.chat.id, "Можно использовать не чаще 1 раза в минуту!")
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
                bot.send_message(call.message.chat.id, "Не удалось получить список песен.")
                return
            song = random.choice(songs)
            title = song.get('title', 'Без названия')
            artist = song.get('artist', '')
            web_url = song.get('web_url', '')
            cover_url = song.get('cover_url', '')
            msg = f"🎲 Песня дня:\n<b>{title}</b> — {artist}\nhttps://www.smule.com{web_url}"
            logging.info(f"Песня дня для {user_id}: {title} — {artist}")
            if cover_url:
                bot.send_photo(call.message.chat.id, cover_url, caption=msg, parse_mode='HTML')
            else:
                bot.send_message(call.message.chat.id, msg, parse_mode='HTML')
        except Exception as e:
            logging.error(f"Ошибка при получении песни дня: {e}")
            bot.send_message(call.message.chat.id, f"Ошибка при получении песни: {e}")
    elif call.data == "button6":
        user_states[user_id] = PROMOTE_STATE
        response_text = "Отправьте ссылку на трек, который хотите пропиарить:"
        image_path = 'piar.png'
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=response_text)
                logging.info(f"Картинка {image_path} отправлена для кнопки Пропиарь меня!.")
            else:
                logging.warning(f"Файл картинки {image_path} не найден для кнопки Пропиарь меня!. Отправляю только текст.")
                bot.send_message(call.message.chat.id, response_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке картинки или текста для кнопки Пропиарь меня!: {e}")
            bot.send_message(call.message.chat.id, response_text)

@bot.message_handler(commands=['meme'])
def send_random_meme_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()

    # Проверяем ограничение на частоту запросов для /meme
    if user_id in last_meme_time and now - last_meme_time[user_id] < 60:
        remaining_time = int(60 - (now - last_meme_time[user_id]))
        bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом мема.")
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
                bot.send_photo(message.chat.id, meme_url)
                logging.info(f"Отправлен мем (Imgflip API): {meme_url}")
                last_meme_time[user_id] = now # Обновляем время последнего запроса
            except Exception as e:
                logging.error(f"Не удалось отправить фото {meme_url} (Imgflip API): {e}")
                bot.reply_to(message, f'Вот случайный мем: {meme_url}')

        else:
            bot.reply_to(message, 'Не удалось получить список мемов от API.')
            logging.warning("Imgflip API не вернул список мемов")

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к Imgflip API: {e}")
        bot.reply_to(message, 'Не удалось подключиться к Imgflip API.')
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при обработке Imgflip API ответа: {e}")
        bot.reply_to(message, 'Произошла ошибка при обработке ответа от Imgflip API.')

@bot.message_handler(commands=['prediction'])
def vocal_predictor(message: types.Message):
    logging.info(f"/prediction в чате {message.chat.id} от {message.from_user.username or message.from_user.id}")
    prediction = get_random_vocal_prediction()
    
    try:
        # Путь к файлу с картинкой
        image_path = 'prediction.png' # Укажите правильный путь, если файл не в той же директории

        # Проверяем, существует ли файл
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                # Отправляем картинку с текстом предсказания в подписи
                bot.send_photo(message.chat.id, photo, caption=f"🧙‍♂️ Вокальный предсказатель:\n{prediction}")
            logging.info(f"Картинка {image_path} отправлена с предсказанием.")
        else:
            # Если файл не найден, отправляем только текст предсказания
            logging.warning(f"Файл картинки {image_path} не найден. Отправляю только текст.")
            bot.reply_to(message, f"🧙‍♂️ Вокальный предсказатель:\n{prediction}")

    except Exception as e:
        logging.error(f"Ошибка при отправке картинки prediction.png или предсказания: {e}")
        bot.reply_to(message, f"Произошла ошибка при получении предсказания: {e}")

@bot.message_handler(commands=['hall'])
def hall_command(message: types.Message):
    logging.info(f"Команда /hall от {message.from_user.username or message.from_user.id}")
    
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.reply_to(message, "Использование: /hall [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            bot.reply_to(message, "Категория должна быть 'legend' или 'cringe'")
            return
        
        nominee = args[2]
        nominator = message.from_user.username or f"id{message.from_user.id}"
        
        # Проверяем, не номинирован ли уже этот пользователь
        hall_data = load_hall_data()
        for row in hall_data:
            if row['name'] == nominee and row['category'] == category:
                bot.reply_to(message, f"@{nominee} уже номинирован в эту категорию!")
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
                bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /hall.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /hall. Отправляю только текст.")
            bot.reply_to(message, response_text)

        logging.info(f"Номинация создана: {response_text}")
        
    except Exception as e:
        logging.error(f"Ошибка в команде /hall: {e}")
        bot.reply_to(message, f"Произошла ошибка при обработке команды: {e}")

@bot.message_handler(commands=['halllist'])
def hall_list(message: types.Message):
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
                bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /halllist.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /halllist. Отправляю только текст.")
            bot.reply_to(message, response_text)
        
        logging.info(f"Список зала славы/позора отправлен: {response_text}")
        
    except Exception as e:
        logging.error(f"Ошибка в команде /halllist: {e}")
        bot.reply_to(message, f"Произошла ошибка при получении списка: {e}")

@bot.message_handler(commands=['vote'])
def vote_command(message: types.Message):
    logging.info(f"Команда /vote от {message.from_user.username or message.from_user.id}")
    
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.reply_to(message, "Использование: /vote [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            bot.reply_to(message, "Категория должна быть 'legend' или 'cringe'")
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
            bot.reply_to(message, f"Номинация для @{nominee} в категории {category} не найдена!")
            return
        
        # Сохраняем обновленные данные
        save_hall_data(hall_data)
        
        category_emoji = "🏆" if category == "legend" else "🤦"
        response_text = f"{category_emoji} Ваш голос за @{nominee} учтен!"

        # Добавляем отправку картинки
        image_path = 'vote.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /vote.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /vote. Отправляю только текст.")
            bot.reply_to(message, response_text)

    except Exception as e:
        logging.error(f"Ошибка в команде /vote: {e}")
        bot.reply_to(message, f"Произошла ошибка при голосовании: {e}")

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
def russian_song_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов
    if user_id in last_russong_time and now - last_russong_time[user_id] < 60:
        remaining_time = int(60 - (now - last_russong_time[user_id]))
        bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом.")
        return
    
    logging.info(f"Команда /random от {message.from_user.username or message.from_user.id}")
    
    title, artist, link = get_random_russian_song()
    if not title:
        bot.reply_to(message, "😔 К сожалению, не удалось найти песню.")
        return
    
    # Обновляем время последнего запроса
    last_russong_time[user_id] = now
        
    response = (
        f"🎵 Случайная песня:\n\n"
        f"<b>{title}</b>\n"
        f"Исполнитель: {artist}\n\n"
        f"Ссылка на Last.fm:\n{link}"
    )
    bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['cat'])
def cat_command(message: types.Message):
    user_id = message.from_user.id
    now = time.time()
    
    # Проверяем ограничение на частоту запросов для /cat
    if user_id in last_cat_time and now - last_cat_time[user_id] < 60:
        remaining_time = int(60 - (now - last_cat_time[user_id]))
        bot.reply_to(message, f"⏳ Подождите {remaining_time} секунд перед следующим запросом котика.")
        return
        
    logging.info(f"Команда /cat от {message.from_user.username or message.from_user.id}")
    
    try:
        # URL для получения случайного изображения котика с заданным размером
        cat_api_url = "http://theoldreader.com/kittens/600/400"
        
        response = requests.get(cat_api_url, timeout=10)
        
        # Проверяем успешность запроса и тип контента (ожидаем изображение)
        if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
            bot.send_photo(message.chat.id, response.content)
            logging.info(f"Изображение котика отправлено в чат {message.chat.id}")
            last_cat_time[user_id] = now # Обновляем время последнего запроса
        else:
            logging.error(f"Не удалось получить изображение котика. Статус: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
            bot.reply_to(message, "😔 Не удалось получить изображение котика. Попробуйте позже.")
            
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /cat: {e}")
        bot.reply_to(message, f"Произошла ошибка при получении котика: {e}")

@bot.message_handler(commands=['casino'])
def casino_command(message: types.Message):
    logging.info(f"Команда /casino от {message.from_user.username or message.from_user.id}")
    
    # Список символов для слотов из пакета DMJSlotMachine2
    symbols = ['🍒', '🍊', '🍋', '🍇', '7️⃣']
    
    # Генерируем 3 случайных символа
    result = [random.choice(symbols) for _ in range(3)]
    
    # Сначала отправляем символы
    bot.reply_to(message, f"🎰 {' '.join(result)} 🎰")
    
    # Проверяем выигрыш (все символы одинаковые)
    if all(x == result[0] for x in result):
        # 10% шанс на выигрыш
        if random.random() < 0.1:
            win_message = (
                f"{'🎉' * 10}\n"
                f"ПОЗДРАВЛЯЕМ С ПОБЕДОЙ! 🎊\n"
                f"{'🎉' * 10}"
            )
            bot.send_message(message.chat.id, win_message)
        else:
            # Если не выпал 10% шанс, отправляем сообщение о проигрыше
            bot.send_message(message.chat.id, "Повезет в следующий раз!")
    else:
        bot.send_message(message.chat.id, "Повезет в следующий раз!")

@bot.message_handler(commands=['help'])
def help_command(message: types.Message):
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
            bot.send_photo(message.chat.id, photo, caption=help_text)
        logging.info(f"Картинка {image_path} отправлена для команды /help.")
    else:
        logging.warning(f"Файл картинки {image_path} не найден для команды /help. Отправляю только текст.")
        bot.reply_to(message, help_text)

@bot.message_handler(func=lambda message: True)
def handle_message(message: types.Message):
    # Логирование в самом начале функции для отладки получения всех сообщений
    logging.info(f"[handle_message start] Получено сообщение от {message.from_user.id}. Chat ID: {message.chat.id}. Content Type: {message.content_type}")
    
    if message.chat.type not in ['private']:
        return
    user_id = message.from_user.id
    
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
        '/random', '/cat', '/meme', '/help', '/casino'
    ]

    # Проверяем, является ли сообщение командой, но не известной
    if message.text and message.text.startswith('/'):
        command = message.text.split()[0] # Извлекаем только саму команду без аргументов
        if command not in known_commands:
            logging.info(f"Неизвестная команда в handle_message от {message.from_user.username or message.from_user.id}: {message.text}")
            bot.reply_to(message, "Неизвестная команда. Используйте /help для списка доступных команд.")
            return # Прекращаем обработку, если команда неизвестна
        # Если это известная команда, она будет обработана соответствующим обработчиком с более высоким приоритетом
        # handle_message просто пропустит ее дальше, что и нужно.

    # FSM: если пользователь пишет анонимку
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"Пользователь {user_id} в ANON_STATE. Проверка типа сообщения.")
        if message.text:
            # Обработка текстовых сообщений
            text = message.text.strip()
            anon_text = f"{text}\n\n#анон"
            for admin_id in ADMIN_IDS:
                bot.send_message(admin_id, f"Новая анонимка на модерацию:\n\n{anon_text}\n\n")
            logging.info(f"Анонимка от {user_id} отправлена на модерацию")
            bot.reply_to(message, "Спасибо! Ваша анонимка отправлена на модерацию.")
            user_states.pop(user_id, None)
            return
        # Если получен не текст в состоянии анонимки, другие обработчики медиа будут вызваны.
        # Если и там не обработается (т.е. не фото и не голос), тогда сработает else ниже.
        # pass # Позволить другим обработчикам сообщений сработать

@bot.message_handler(content_types=['photo'])
def handle_anon_photo(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"[handle_anon_photo] Получена фотография от {user_id} в ANON_STATE.")
        # Обработка фотографий
        photo_id = message.photo[-1].file_id  # Берем последнюю (самую большую) версию фото
        caption = message.caption or ""
        anon_text = f"{caption}\n\n#анон" if caption else "#анон"
        try:
            for admin_id in ADMIN_IDS:
                bot.send_photo(admin_id, photo_id, caption=anon_text)
            logging.info(f"Анонимная фотография от {user_id} успешно отправлена на модерацию")
            bot.reply_to(message, "Спасибо! Ваша анонимная фотография отправлена на модерацию.")
        except Exception as e:
            logging.error(f"[handle_anon_photo] Ошибка при отправке фото админам: {e}")
            bot.reply_to(message, "Произошла ошибка при отправке фотографии. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return
    # else: # Если не в ANON_STATE, позволяем сообщению пройти к другим обработчикам фото
    #     pass

@bot.message_handler(content_types=['voice'])
def handle_anon_voice(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) == ANON_STATE:
        logging.info(f"[handle_anon_voice] Получено голосовое сообщение от {user_id} в ANON_STATE.")
        # Обработка голосовых сообщений
        voice_id = message.voice.file_id
        caption = message.caption or ""
        anon_text = f"{caption}\n\n#анон" if caption else "#анон"
        try:
            for admin_id in ADMIN_IDS:
                bot.send_voice(admin_id, voice_id, caption=anon_text)
            logging.info(f"Анонимное голосовое сообщение от {user_id} успешно отправлено на модерацию")
            bot.reply_to(message, "Спасибо! Ваше анонимное голосовое сообщение отправлено на модерацию.")
        except Exception as e:
            logging.error(f"[handle_anon_voice] Ошибка при отправке голосового сообщения админам: {e}")
            bot.reply_to(message, "Произошла ошибка при отправке голосового сообщения. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

@bot.message_handler(content_types=['sticker'])
def handle_sticker(message: types.Message):
    sticker_id = message.sticker.file_id
    emoji = message.sticker.emoji
    logging.info(f"Получен стикер с file_id: {sticker_id}, эмодзи: {emoji}")
    bot.reply_to(message, f"File ID стикера: {sticker_id}\nЭмодзи: {emoji}")

@bot.message_handler(content_types=['dice'])
def handle_dice(message: types.Message):
    dice_id = message.dice.file_id
    emoji = message.dice.emoji
    logging.info(f"Получено анимированное эмодзи (Dice) с file_id: {dice_id}, эмодзи: {emoji}")
    bot.reply_to(message, f"File ID анимированного эмодзи: {dice_id}\nЭмодзи: {emoji}")

    # FSM: если пользователь предлагает песню
    if user_states.get(user_id) == SONG_STATE:
        text = message.text.strip()
        if len(text) > 500:
            bot.reply_to(message, "Слишком длинно! Пожалуйста, до 500 символов.")
            return
        user_info = f"@{message.from_user.username}" if message.from_user.username else f"id: {user_id}"
        for admin_id in ADMIN_IDS:
            bot.send_message(admin_id, f"Новое предложение песни:\n\n{text}\n\nОт пользователя: {user_info}")
        logging.info(f"Песня предложена {user_id}")
        bot.reply_to(message, "Спасибо! Ваше предложение отправлено на рассмотрение.")
        user_states.pop(user_id, None)
        return
    # FSM: если пользователь отправляет ссылку для оценки
    if user_states.get(user_id) == RATE_LINK_STATE:
        link = message.text.strip()
        if not (link.startswith("http://") or link.startswith("https://")):
            bot.reply_to(message, "Пожалуйста, отправьте корректную ссылку на трек.")
            return
        user_info = f"@{message.from_user.username}" if message.from_user.username else f"id: {user_id}"
        for admin_id in ADMIN_IDS:
            bot.send_message(admin_id, f"Запрос на оценку исполнения:\n\nСсылка: {link}\n\nОт пользователя: {user_info}")
        logging.info(f"Оценка трека запрошена {user_id}")
        bot.reply_to(message, "Спасибо! Ваш запрос на оценку отправлен.")
        user_states.pop(user_id, None)
        return
    # FSM: если пользователь отправляет ссылку для промо
    if user_states.get(user_id) == PROMOTE_STATE:
        track_link = message.text.strip()

        # Простая проверка на формат ссылки
        if not (track_link.startswith("http://") or track_link.startswith("https://")):
            bot.reply_to(message, "Пожалуйста, отправьте корректную ссылку на трек.")
            return

        user_info = f"@{message.from_user.username}" if message.from_user.username else f"id: {message.from_user.id}"
        request_id = str(uuid.uuid4()) # Генерируем уникальный ID запроса

        # Сохраняем данные запроса временно
        pending_promotions[request_id] = {
            "user_id": message.from_user.id,
            "user_info": user_info,
            "track_link": track_link
        }

        # Шаблон сообщения для администратора
        admin_message_text = (
            f"📢 Новый запрос на промо от {user_info}:\n\n"
            f"Трек: {track_link}\n\n"
        )
        
        # Отправляем сообщение админам на модерацию (без кнопки)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, admin_message_text)
            except Exception as admin_e:
                logging.error(f"Не удалось отправить сообщение админу {admin_id}: {admin_e}")
            
        logging.info(f"Запрос на промо от {user_info} (ID: {request_id}) отправлен на модерацию.")
        bot.reply_to(message, "Спасибо! Ваш запрос на промо отправлен администраторам на модерацию.")
        user_states.pop(user_id, None) # Сбрасываем состояние после получения ссылки
        return # Важно выйти после обработки состояния

    logging.info(f"Сообщение вне сценария от {user_id} в чате {message.chat.id}")
    bot.reply_to(message, "Я вас слушаю! Используйте команду /start для начала работы.")

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

def main():
    """Основная функция запуска бота"""
    if not ALLOWED_GROUP_ID:
        logging.error("ALLOWED_GROUP_ID не установлен в .env файле!")
        return

    # Запускаем бота
    bot.infinity_polling()

if __name__ == '__main__':
    main() 