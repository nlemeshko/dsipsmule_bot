#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регистрация на конкурс NASSAL2026.
"""

from telegram import Update
from telegram.ext import ContextTypes

from commands.callback_handler import (
    user_states,
    NASSAL_NICK_STATE,
    NASSAL_CATEGORY_STATE,
)
from commands.common import build_binary_stream


NASSAL_IMAGE_PATH = 'images/nassal2026.png'

NASSAL_WELCOME_TEXT = """🏆 <b>Добро пожаловать на конкурс NASSAL2026!</b>

Сегодня мы открываем регистрацию участников.
Чтобы всё оформить красиво и без путаницы, я задам тебе два коротких вопроса.

<b>Шаг 1 из 2.</b>
Напиши, пожалуйста, свой <b>ник в Smule</b>.

После этого я попрошу выбрать корзину участника."""

NASSAL_CATEGORY_TEXT = """🎤 <b>Отлично, я записал твой ник в Smule.</b>

<b>Шаг 2 из 2.</b>
Теперь отправь <b>число от 1 до 4</b>, чтобы выбрать свою корзину:

<b>1</b> — вокалисты
<b>2</b> — реперы
<b>3</b> — рокеры
<b>4</b> — приколисты

Просто пришли одно число сообщением."""

NASSAL_SUCCESS_TEXT = """✅ <b>Регистрация завершена!</b>

Спасибо за участие.
Вы успешно зарегистрированы на конкурс <b>NASSAL2026</b>!

Совсем скоро администраторы увидят вашу заявку и свяжутся с вами при необходимости."""

NASSAL_CATEGORY_LABELS = {
    "1": "Вокалисты",
    "2": "Реперы",
    "3": "Рокеры",
    "4": "Приколисты",
}


async def send_nassal_intro(context: ContextTypes.DEFAULT_TYPE, chat_id: int, reply_to_message_id: int | None = None):
    """Отправляет приветствие для регистрации NASSAL2026."""
    photo = build_binary_stream(NASSAL_IMAGE_PATH)
    if photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=NASSAL_WELCOME_TEXT,
            parse_mode='HTML',
            reply_to_message_id=reply_to_message_id,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=NASSAL_WELCOME_TEXT,
            parse_mode='HTML',
            reply_to_message_id=reply_to_message_id,
        )


async def start_nassal_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает пошаговую регистрацию на конкурс."""
    user_id = update.effective_user.id
    chat = update.effective_chat
    msg = update.effective_message

    if not chat or chat.type != "private":
        await msg.reply_text(
            "Регистрация на NASSAL2026 доступна в личных сообщениях с ботом. Напишите мне в личку и отправьте /nassal2026."
        )
        return

    user_states[user_id] = NASSAL_NICK_STATE
    context.user_data.pop("nassal_registration", None)

    reply_to_message_id = msg.message_id if msg else None
    await send_nassal_intro(context, chat.id, reply_to_message_id=reply_to_message_id)


async def nassal2026_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда запуска регистрации на конкурс NASSAL2026."""
    await start_nassal_registration(update, context)
