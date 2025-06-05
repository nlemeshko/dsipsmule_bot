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
# Читаем ALLOWED_GROUP_ID как строку, разделенную запятыми
allowed_groups_str = os.getenv('ALLOWED_GROUP_ID', '')
# Преобразуем строку в список целых чисел
ALLOWED_GROUP_IDS = [int(group_id.strip()) for group_id in allowed_groups_str.split(',') if group_id.strip()]
CHARACTER_AI_TOKEN = os.getenv('CHARACTER_AI_TOKEN')
CHARACTER_ID = "P5xPFx4UhFQ-jcbMRwofQBkXijxNSo6NOYbPHCT4auE"
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

# Получение Client-ID Imgur из переменных окружения
IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')

# Список ответов для команды /proof
proof_agree_responses = [
    "Ооо, наконец-то кто-то сказал что-то умное! Полностью согласен!",
    "Бро, ты гений! Это именно то, что я хотел сказать!",
    "Да ты что, это же очевидно! Конечно согласен!",
    "Наконец-то кто-то додумался до этого! Подписываюсь под каждым словом!",
    "О, смотрите кто у нас тут умный! И правда, согласен на все 100%!",
    "Вау, ты читаешь мои мысли? Абсолютно верно!",
    "Да ты что, это же элементарно! Конечно согласен!",
    "Ооо, кто-то тут умный! Полностью поддерживаю!",
    "Наконец-то кто-то сказал правду! Согласен на все 200%!",
    "Бро, ты прям в точку! Это именно то, что я думал!"
]

proof_disagree_responses = [
    "Бро, ты что, с луны свалился? Это же полная чушь!",
    "Ооо, кто-то тут пересмотрел сериалов! Не верю ни единому слову!",
    "Да ты что, это же как дважды два - пять! Полный бред!",
    "Ой, кто-то тут перегрелся на солнце! Это не так работает!",
    "Бро, может тебе отдохнуть? Это же полная ерунда!",
    "Ооо, смотрите кто у нас тут фантазёр! Не верю ни капли!",
    "Да ты что, это же как квадратное яйцо! Полный абсурд!",
    "Ой, кто-то тут переел сладкого! Это не имеет смысла!",
    "Бро, может тебе выспаться? Это же полная чушь!",
    "Ооо, кто-то тут переиграл в игры! Это нереально!"
]

proof_unsure_responses = [
    "Хмм... Может ты прав, а может и нет. Кто его знает?",
    "Ооо, сложный вопрос! Может быть да, а может быть нет...",
    "Бро, ты меня в тупик поставил! Нужно подумать...",
    "Хмм... Интересная мысль, но я не уверен. Может быть...",
    "Ой, кто-то тут задал сложный вопрос! Давай подумаем вместе..."
]

# Список ответов для команды /roast
roast_responses = [
    "{user_nick}, твоя остроумность застряла где-то между 'привет' и 'пока'.",
    "Ого, {user_nick}! Ты, наверное, единственный, кто может провалить даже тест на IQ в отрицательную сторону.",
    "{user_nick}, у тебя лицо такое, будто ты пытался поймать муху ртом и проглотил ее с первого раза.",
    "Слушай, {user_nick}, когда раздавали мозги, ты, видимо, стоял в очереди за чувством юмора.",
    "{user_nick}, ты как понедельник утром – никто тебе не рад.",
    "У {user_nick} столько харизмы, сколько у меня терпения объяснять это.",
    "{user_nick}, ты не грустный, у тебя просто лицо такое.",
    "{user_nick}, я не говорю, что ты странный, но с тобой даже тараканы здороваются за руку.",
    "Твоя логика, {user_nick}, как швейцарский сыр – вся в дырках.",
    "{user_nick}, ты доказательство того, что эволюция иногда делает перерывы.",
    "Мне кажется, {user_nick}, ты единственный, кто может споткнуться на ровном месте и упасть вверх.",
    "{user_nick}, твои шутки такие старые, что их слушали еще динозавры.",
    "Я не эксперт, {user_nick}, но, кажется, у тебя аллергия на успех.",
    "{user_nick}, ты выглядишь так, будто только что боролся с медведем... и проиграл.",
    "{user_nick}, если бы глупость светилась, ты бы освещал целый город.",
    "Мне сказали, {user_nick}, что у тебя золотое сердце. Надеюсь, это не единственное золото, что у тебя есть.",
    "{user_nick}, ты как просроченный йогурт – лучше держаться подальше.",
    "Я пытался найти твои положительные стороны, {user_nick}, но заблудился в темноте.",
    "{user_nick}, ты не забыл сегодня надеть штаны? Просто интересуюсь.",
    "Говорят, смех продлевает жизнь. Глядя на тебя, {user_nick}, я чувствую себя бессмертным.",
    "{user_nick}, твои идеи такие же свежие, как вчерашний хлеб!",
    "{user_nick}, ты единственный, кто может упасть вверх по лестнице!",
    "{user_nick}, твои шутки такие плоские, что даже блин выглядит объемным!",
    "{user_nick}, ты настолько медленный, что даже черепаха предлагает тебе подвезти!",
    "{user_nick}, твои навыки такие же полезные, как зонтик в пустыне!"
]

# Список предсказаний для команды /prediction
prediction_responses = [
    "Тебя ждет неожиданная встреча со старым другом.",
    "В ближайшее время тебя ожидает приятный сюрприз.",
    "Твои мечты скоро станут реальностью.",
    "Тебя ждет успех в профессиональной сфере.",
    "Впереди тебя ждет увлекательное путешествие.",
    "Твои творческие идеи будут высоко оценены.",
    "Тебя ждет период финансового благополучия.",
    "В ближайшее время ты найдешь решение давней проблемы.",
    "Тебя ждет встреча с интересным человеком.",
    "Твои усилия скоро будут вознаграждены.",
    "Тебя ждет неожиданное признание твоих талантов.",
    "Впереди тебя ждет период личностного роста.",
    "Твои планы будут реализованы успешно.",
    "Тебя ждет приятное знакомство с новыми людьми.",
    "В ближайшее время ты получишь важное известие.",
    "Тебя ждет успех в новом начинании.",
    "Твои мечты окажутся ближе, чем ты думаешь.",
    "Впереди тебя ждет период вдохновения и творчества.",
    "Тебя ждет неожиданная помощь от близких.",
    "Твои усилия приведут к значительным результатам.",
    "Тебя ждет неожиданное предложение, от которого сложно отказаться.",
    "В ближайшее время ты откроешь в себе новые таланты.",
    "Твои мечты окажутся даже лучше, чем ты представлял.",
    "Тебя ждет период гармонии и душевного спокойствия.",
    "Впереди тебя ждет встреча, которая изменит твою жизнь.",
    "Твои творческие идеи приведут к неожиданному успеху.",
    "Тебя ждет период, когда все будет складываться как нельзя лучше.",
    "В ближайшее время ты получишь признание, которого заслуживаешь.",
    "Твои планы превзойдут все ожидания.",
    "Тебя ждет неожиданный поворот судьбы к лучшему."
]

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
    logging.info(f"Command /start received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
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
    logging.info(f"Callback query received: {call.data} from user {call.from_user.username or call.from_user.id} in chat {call.message.chat.id}")
    logging.info(f"Кнопка: {call.data} от {call.from_user.username or call.from_user.id} в чате {call.message.chat.id}")
    await bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "button1":
        user_states[user_id] = ANON_STATE
        logging.info(f"Установлено состояние ANON_STATE для пользователя {user_id}")
        response_text = "Отправьте текст, фотографию или голосовое сообщение для анонимки:"
        image_path = 'images/anon.png'
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
        image_path = 'images/sing.png'
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
        image_path = 'images/rate.png'
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
        image_path = 'images/piar.png'
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
    logging.info(f"Command /meme received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
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
    logging.info(f"Command /prediction received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    logging.info(f"/prediction в чате {message.chat.id} от {message.from_user.username or message.from_user.id}")
    prediction = get_random_vocal_prediction()
    
    try:
        # Путь к файлу с картинкой
        image_path = 'images/prediction.png'

        # Проверяем, существует ли файл
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                # Отправляем картинку с текстом предсказания в подписи
                await bot.send_photo(
                    message.chat.id, 
                    photo, 
                    caption=f"🧙‍♂️ Вокальный предсказатель:\n{prediction}",
                    reply_to_message_id=message.message_id # Добавляем reply_to_message_id
                )
            logging.info(f"Картинка {image_path} отправлена с предсказанием как ответ.")
        else:
            # Если файл не найден, отправляем только текст предсказания как ответ
            logging.warning(f"Файл картинки {image_path} не найден. Отправляю только текст как ответ.")
            await bot.reply_to(message, f"🧙‍♂️ Вокальный предсказатель:\n{prediction}")

    except Exception as e:
        logging.error(f"Ошибка при отправке картинки {image_path} или предсказания: {e}")
        await bot.reply_to(message, f"Произошла ошибка при получении предсказания: {e}")

@bot.message_handler(commands=['hall'])
async def hall_command(message: types.Message):
    logging.info(f"Command /hall received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    hall_data = load_hall_data()
    
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
        image_path = 'images/hall.png'
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
    logging.info(f"Command /halllist received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    hall_data = load_hall_data()
    
    try:
        logging.info(f"Команда /halllist от {message.from_user.username or message.from_user.id}")
        
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
        image_path = 'images/halllist.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(message.chat.id, photo, caption=response_text)
            logging.info(f"Картинка {image_path} отправлена для команды /halllist.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /halllist. Отправляю только текст.")
            await bot.reply_to(message, response_text)
        
        logging.info(f"Список зала славы/позора отправлен: {response_text}")
        
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                # Отправляем картинку с текстом предсказания в подписи как ответ на сообщение
                await bot.send_photo(
                    message.chat.id, 
                    photo, 
                    caption=response_text,
                    reply_to_message_id=message.message_id # Добавляем reply_to_message_id
                )
            logging.info(f"Картинка {image_path} отправлена как ответ для команды /halllist.")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /halllist. Отправляю только текст как ответ.")
            await bot.reply_to(message, response_text)
        
    except Exception as e:
        logging.error(f"Ошибка в команде /halllist: {e}")
        await bot.reply_to(message, f"Произошла ошибка при получении списка: {e}")

@bot.message_handler(commands=['vote'])
async def vote_command(message: types.Message):
    logging.info(f"Command /vote received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    hall_data = load_hall_data()
    
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
        image_path = 'images/vote.png'
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
    logging.info(f"Command /random received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    # Ограничение по времени для команды /random
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
    logging.info(f"Command /cat received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    # Ограничение по времени для команды /cat
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
    logging.info(f"Command /casino received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
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
    image_path = 'images/casino.png'
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
    logging.info(f"Command /help received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    help_text = (
        "Список доступных команд:\n\n"
        "/start - Начать взаимодействие с ботом\n"
        "/help - Показать это сообщение помощи\n"
        "/prediction - Получить вокальное предсказание\n"
        "/hall [legend/cringe] [имя пользователя] - Номинировать пользователя в Зал славы/позора\n"
        "/halllist - Посмотреть списки Зала славы/позора\n"
        "/vote [legend/cringe] [имя пользователя] - Проголосовать за номинанта\n"
        "/random - Получить случайную русскую песню с Last.fm\n"
        "/cat - Получить случайное изображение котика\n"
        "/meme - Получить случайный мем\n"
        "/casino - Сыграть в слоты с анимированными символами\n"
        "/pole - Сыграть в Поле чудес с голосовыми подсказками\n"
        "/ask [вопрос] - Задать вопрос AI-персонажу\n"
        "/roast - Получить критику исполнения\n"
        "/proof - Подтвердить исполнение\n\n"
        "Также доступны функции через кнопки в главном меню (/start) в общении с @dsipsmule_bot:\n"
        "🕵 Анонимка - Отправить анонимное сообщение\n"
        "🎶 Песня - Предложить песню\n"
        "🎧 Оценить - Оценить исполнение\n"
        "🎲 Песня дня - Получить случайную песню дня\n"
        "📢 Промо - Отправить промо-запрос"
    )
    
    # Добавляем отправку картинки
    image_path = 'images/help.png'
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await bot.send_photo(message.chat.id, photo, caption=help_text)
        logging.info(f"Картинка {image_path} отправлена для команды /help.")
    else:
        logging.warning(f"Файл картинки {image_path} не найден для команды /help. Отправляю только текст.")
        await bot.reply_to(message, help_text)

@bot.message_handler(commands=['pole'])
async def pole_command(message: types.Message):
    logging.info(f"Command /pole received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    chat_id = message.chat.id
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
    image_path = 'images/pole.png'
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

@bot.message_handler(content_types=['text', 'caption'], func=lambda message: message.text and not message.text.startswith('/'))
async def handle_message(message: types.Message):
    # Логирование в самом начале функции для отладки получения всех сообщений
    logging.info(f"[handle_message] Received message from user {message.from_user.username or message.from_user.id} ({message.from_user.first_name} {message.from_user.last_name or ''}) in chat {message.chat.id} ({message.chat.type}): {message.text or message.caption}")
    logging.info(f"[handle_message] message.chat.id: {message.chat.id}, message.chat.type: {message.chat.type}")
    if message.reply_to_message:
        logging.info(f"[handle_message] Reply message detected. reply_to_message.message_id: {message.reply_to_message.message_id}")
        if message.reply_to_message.sender_chat:
             logging.info(f"[handle_message] Reply sender_chat.id: {message.reply_to_message.sender_chat.id}, reply sender_chat.type: {message.reply_to_message.sender_chat.type}")
        if message.reply_to_message.chat:
             logging.info(f"[handle_message] Reply chat.id: {message.reply_to_message.chat.id}, Reply chat.type: {message.reply_to_message.chat.type}")

    # Явная проверка: если сообщение является командой, пропускаем его обработку в handle_message
    if message.text and message.text.startswith('/'):
        logging.info(f"Сообщение от {message.from_user.id} является командой: {message.text}. Пропускаем handle_message.")
        return

    user_id = message.from_user.id
    is_private_chat = message.chat.type == 'private'
    
    # Проверяем, играет ли пользователь в "Поле чудес" И сообщение является либо:
    # 1. ответом на сообщение бота в игре (в группе)
    # 2. текстовым сообщением в личном чате (только если пользователь в игре Pole)
    if user_id in pole_games:
        game = pole_games[user_id]
        
        # Проверяем, находится ли сообщение в том же чате, где началась игра
        if message.chat.id != game['chat_id']:
            logging.info(f"Сообщение от игрока {user_id} в другом чате ({message.chat.id}) во время игры в чате {game['chat_id']}. Игнорируем в контексте игры.")
            return # Игнорируем сообщение, если оно не из чата игры

        is_reply_to_bot_game_message = message.reply_to_message and game.get('bot_message_ids') and message.reply_to_message.message_id in game['bot_message_ids']

        # Обрабатываем как ход в игре только если это ответ в группе ИЛИ прямое текстовое сообщение в личном чате
        if (not is_private_chat and is_reply_to_bot_game_message) or (is_private_chat and message.text):
            guess = message.text.lower().strip() if message.text else '' # Берем текст из цитирующего сообщения или прямо из сообщения в ЛС
            logging.info(f"Обрабатываем как ход в Поле чудес. Цитата в группе: {not is_private_chat}, Сообщение в ЛС: {is_private_chat}. Угадывание: {guess}")

            # Если guess пустой после обрезки (например, пустая цитата или сообщение только с пробелами)
            if not guess:
                response = "Пожалуйста, введите букву или слово для угадывания." + (" в цитируемом сообщении." if not is_private_chat else "")
                await bot.reply_to(message, response)
                return # Выходим, не обрабатывая пустой ввод

            # Отправляем сообщение о том, что бот думает
            thinking_msg = await bot.reply_to(message, "🤔 Думаю...")
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
                    del pole_games[user_id]
                    # Отправляем голосовое сообщение победы
                    try:
                        with open('pole/win.mp3', 'rb') as voice:
                            await bot.send_voice(message.chat.id, voice)
                        # Не добавляем ID победного сообщения в bot_message_ids, так как игра окончена
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
                        # ID голосовых сообщений не добавляем в bot_message_ids, т.к. их не цитируют для хода
                        await send_random_voice(bot, message.chat.id, 'pole', 'yes', 3)
                    else:
                        response = "❌ Неверно! Такой буквы нет в слове." + (" Цитатой." if not is_private_chat else "")
                        # Отправляем случайное голосовое сообщение неверного ответа
                        # ID голосовых сообщений не добавляем в bot_message_ids, т.k. их не цитируют для хода
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
                            # Не добавляем ID победного сообщения в bot_message_ids, так как игра окончена
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
            return # Возвращаемся после обработки хода в игре

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

    # Если сообщение не является командой и не соответствует FSM состояниям,
    # но связано с игрой Pole Chudes (как ответ или в ЛС),
    # то оно уже было обработано выше.
    # Если сообщение не является командой, не связано с игрой Pole Chudes, и не соответствует FSM состояниям,
    # то это обычное текстовое/caption сообщение, которое можно проигнорировать или обработать как-то иначе.
    logging.info(f"Сообщение от {user_id} не является командой, не связано с игрой Pole Chudes, и не соответствует FSM состоянию. Игнорируем.")
    # Можно добавить здесь обработку других типов сообщений, если нужно.
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
        return random.choice(prediction_responses)
    except Exception as e:
        logging.error(f"Ошибка при получении предсказания: {e}")
        return "🔮 Не удалось получить предсказание."

@bot.message_handler(commands=['ask'])
async def ask_command(message: types.Message):
    logging.info(f"Command /ask received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    user_id = message.from_user.id
    now = time.time()

    logging.info(f"[ask_command start] Вызвана команда /ask пользователем {user_id} в чате {message.chat.id}")

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
        # Создание клиента CharacterAI
        client = await get_client(token=CHARACTER_AI_TOKEN)
        logging.info("Клиент CharacterAI создан успешно.")

        try:
            logging.info(f"Создаем чат с персонажем ID: {CHARACTER_ID}...")
            # Метод create_chat возвращает кортеж: (Chat object, Turn object)
            # Первый элемент кортежа - это Chat object
            chat_response_tuple = await client.chat.create_chat(CHARACTER_ID)
            chat_object = chat_response_tuple[0] # This is a Chat object
            
            # *** ИСПРАВЛЕНИЕ ОШИБКИ: 'Chat' object has no attribute 'chat' ***
            # Ошибка возникала здесь, потому что мы пытались получить доступ к chat_id через chat_object.chat.id
            # Правильный способ получить ID чата из Chat object - это использовать атрибут .id напрямую
            chat_id = chat_object.chat_id 
            # ****************************************************************
            
            logging.info(f"Чат с персонажем {CHARACTER_ID} создан. Chat ID: {chat_id}")

            logging.info(f"Отправляем сообщение в чат {chat_id} с вопросом: {question}...")
            # Вызываем send_message на client.chat и передаем необходимые аргументы
            # Этот вызов возвращает Turn object
            question_full="Тебя в чате спрашивают "+question
            response = await client.chat.send_message(CHARACTER_ID, chat_id, question_full)
            logging.info(f"Сообщение отправлено. Получен ответ от CharacterAI.")
            
            # turn_id и primary_candidate_id получаем напрямую из объекта Turn (response)
            turn_id = response.turn_id
            primary_candidate_id = response.primary_candidate_id
            reply = response.get_primary_candidate().text
            logging.info(f"CharacterAI: Получен текстовый ответ: {reply}")

            logging.info(f"Генерируем голосовой ответ для chat_id: {chat_id}, turn_id: {turn_id}, primary_candidate_id: {primary_candidate_id}, voice_id: {CHARACTER_VOICE_ID}...")
            # Используем переменную client, созданную выше, и корректные ID
            speech = await client.utils.generate_speech(chat_id, turn_id, primary_candidate_id, CHARACTER_VOICE_ID)
            logging.info("Голосовой ответ сгенерирован успешно.")

            # Отправляем голосовое сообщение пользователю
            logging.info("Отправляем голосовое сообщение пользователю...")
            await bot.send_voice(message.chat.id, speech)
            logging.info("Голосовое сообщение отправлено успешно.")

            # Отправляем изображение ask.png
            image_path = 'images/ask.png'
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
            logging.error(f"[CharacterAI Interaction Error] Ошибка при работе с CharacterAI: {str(e)}")
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
        logging.error(f"[CharacterAI Client Error] Ошибка при создании клиента CharacterAI: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        await bot.delete_message(message.chat.id, thinking_msg.message_id)
        await bot.reply_to(message, f"Произошла ошибка при подключении к CharacterAI: {str(e)}")

@bot.message_handler(commands=['proof'])
async def proof_command(message: types.Message):
    logging.info(f"Command /proof received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    
    if not message.reply_to_message:
        await bot.reply_to(message, "Эта команда работает только в ответ на сообщение!")
        return
    
    # Получаем текст сообщения, на которое отвечаем
    replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    if not replied_text:
        await bot.reply_to(message, "Я могу оценить только текстовые сообщения!")
        return
    
    # Выбираем случайный ответ
    response = random.choice(proof_agree_responses + proof_disagree_responses + proof_unsure_responses)
    
    # Отправляем изображение и текст как ответ на исходное сообщение
    try:
        image_path = 'images/proof.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(
                    message.chat.id,
                    photo,
                    caption=response,
                    reply_to_message_id=message.reply_to_message.message_id
                )
            logging.info(f"Картинка {image_path} отправлена с ответом для команды /proof")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /proof. Отправляю только текст.")
            await bot.reply_to(message.reply_to_message, response)
    except Exception as e:
        logging.error(f"Ошибка при отправке картинки в команде /proof: {e}")
        await bot.reply_to(message.reply_to_message, response)

@bot.message_handler(commands=['roast'])
async def roast_command(message: types.Message):
    logging.info(f"[roast_command] Command /roast received from user {message.from_user.username or message.from_user.id} in chat {message.chat.id}")
    logging.info(f"[roast_command] message.chat.id: {message.chat.id}, message.chat.type: {message.chat.type}")
    if message.reply_to_message:
        logging.info(f"[roast_command] Reply message detected. reply_to_message.message_id: {message.reply_to_message.message_id}")
        if message.reply_to_message.sender_chat:
             logging.info(f"[roast_command] Reply sender_chat.id: {message.reply_to_message.sender_chat.id}, reply sender_chat.type: {message.reply_to_message.sender_chat.type}")
        if message.reply_to_message.chat:
             logging.info(f"[roast_command] Reply chat.id: {message.reply_to_message.chat.id}, Reply chat.type: {message.reply_to_message.chat.type}")

    if message.reply_to_message:
        replied_message = message.reply_to_message
        # Проверяем, является ли сообщение ответом на сообщение из канала или от пользователя
        if replied_message.sender_chat:
            # Если сообщение из канала или группы (от имени чата)
            user_nick = replied_message.sender_chat.title
        else:
            # Если сообщение от пользователя
            user_nick = replied_message.from_user.first_name or replied_message.from_user.username
        reply_id = replied_message.message_id
    else:
        # Если это не ответ на сообщение, прожариваем пользователя, который ввел команду
        user_nick = message.from_user.first_name or message.from_user.username
        reply_id = message.message_id

    if not user_nick:
        user_nick = "дорогой друг"

    # Выбираем случайный ответ и подставляем никнейм
    response = random.choice(roast_responses).format(user_nick=user_nick)
    
    # Отправляем изображение и текст как ответ на соответствующее сообщение
    try:
        image_path = 'images/roast.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await bot.send_photo(
                    message.chat.id,
                    photo,
                    caption=response,
                    reply_to_message_id=reply_id
                )
            logging.info(f"Картинка {image_path} отправлена с ответом для команды /roast")
        else:
            logging.warning(f"Файл картинки {image_path} не найден для команды /roast. Отправляю только текст.")
            await bot.send_message(message.chat.id, response, reply_to_message_id=reply_id)
    except Exception as e:
        logging.error(f"Ошибка при отправке картинки в команде /roast: {e}")
        await bot.send_message(message.chat.id, response, reply_to_message_id=reply_id)

def main():
    """Основная функция запуска бота"""
    if not ALLOWED_GROUP_IDS:
        logging.error("ALLOWED_GROUP_IDS не установлен в .env файле!")
        return

    # Запускаем бота
    asyncio.run(bot.polling(non_stop=True))

if __name__ == '__main__':
    main() 