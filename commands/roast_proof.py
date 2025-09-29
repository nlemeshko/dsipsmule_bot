#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команды /roast и /proof
"""

import os
import random
from telegram import Update
from telegram.ext import ContextTypes

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

async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /proof"""
    
    # Определяем message_id, на которое будет отвечать бот
    # Если это ответ на другое сообщение, отвечаем на него
    # Иначе (если команда пришла без ответа), отвечаем на само сообщение с командой
    reply_to_message_id = update.message.reply_to_message.message_id if update.message.reply_to_message else update.message.message_id

    # Выбираем случайный ответ
    response = random.choice(proof_agree_responses + proof_disagree_responses + proof_unsure_responses).format(
        user_nick=update.effective_user.first_name or update.effective_user.username or "дорогой друг"
    )

    # Отправляем изображение и текст как ответ на соответствующее сообщение
    try:
        image_path = 'images/proof.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo,
                    caption=response,
                    reply_to_message_id=reply_to_message_id
                )
            print(f"Картинка {image_path} отправлена с ответом для команды /proof с reply_to_message_id={reply_to_message_id}.")
        else:
            print(f"Файл картинки {image_path} не найден для команды /proof. Отправляю только текст как ответ.")
            await update.message.reply_text(response, reply_to_message_id=reply_to_message_id)
    except Exception as e:
        print(f"Ошибка при отправке картинки в команде /proof: {e}")
        await update.message.reply_text(response, reply_to_message_id=reply_to_message_id)

async def roast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /roast"""
    
    if update.message.reply_to_message:
        replied_message = update.message.reply_to_message
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
        user_nick = update.effective_user.first_name or update.effective_user.username
        reply_id = update.message.message_id

    if not user_nick:
        user_nick = "дорогой друг"

    # Выбираем случайный ответ и подставляем никнейм
    response = random.choice(roast_responses).format(user_nick=user_nick)
    
    # Отправляем изображение и текст как ответ на соответствующее сообщение
    try:
        image_path = 'images/roast.png'
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo,
                    caption=response,
                    reply_to_message_id=reply_id
                )
            print(f"Картинка {image_path} отправлена с ответом для команды /roast")
        else:
            print(f"Файл картинки {image_path} не найден для команды /roast. Отправляю только текст.")
            await update.message.reply_text(response, reply_to_message_id=reply_id)
    except Exception as e:
        print(f"Ошибка при отправке картинки в команде /roast: {e}")
        await update.message.reply_text(response, reply_to_message_id=reply_id)
