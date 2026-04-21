#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регистрация на вокальный конкурс NASSAL2026.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from commands.callback_handler import (
    user_states,
    NASSAL_NAMES_STATE,
)
from commands.common import build_binary_stream


NASSAL_IMAGE_PATH = 'images/nassal2026.png'
NASSAL_JOIN_URL = "https://t.me/+vl1RPF8Q2RZmY2Ey"

NASSAL_BASKETS = {
    "1": {
        "name": "Корзина имени Гены Букина",
        "role": "Вокалисты",
        "image_path": "images/nassal_gena.png",
    },
    "2": {
        "name": "Корзина имени Светы Букиной",
        "role": "Рокеры",
        "image_path": "images/nassal_sveta.png",
    },
    "3": {
        "name": "Корзина имени Ромы Букина",
        "role": "Реперы",
        "image_path": "images/nassal_roma.png",
    },
    "4": {
        "name": "Корзина имени Даши Букиной",
        "role": "Приколисты",
        "image_path": "images/nassal_dasha.png",
    },
}

YES_ANSWERS = {"да", "yes", "y", "верно", "подтверждаю", "ок", "окей", "угу"}
NO_ANSWERS = {"нет", "no", "n", "неверно", "исправить", "заново"}

NASSAL_WELCOME_TEXT = """🏆 <b>Добро пожаловать на NASSAL2026</b>

<b>National Artist Singing Smule Award League 2026</b> — это вокальный конкурс для ярких голосов, смелых дуэтов и артистов со своим стилем.

Маскоты сезона — герои вселенной <b>«Счастливы вместе»</b>, а я помогу оформить заявку аккуратно и по шагам.

<b>Шаг 1 из 5.</b>
Напиши <b>одно или два имени участников</b>.

Если это сольная заявка — укажи одно имя.
Если это дуэт — укажи два имени одним сообщением."""

NASSAL_SMULE_TEXT = """🎙️ <b>Отлично, имена записаны.</b>

<b>Шаг 2 из 5.</b>
Теперь напиши ваш <b>ник в Smule</b>.

Если регистрируется дуэт, можно указать общий ник дуэта или основной ник для связи."""

NASSAL_AVATAR_TEXT = """🖼️ <b>Принято.</b>

<b>Шаг 3 из 5.</b>
Теперь пришли <b>аватар</b> участника или дуэта одной фотографией.

Это изображение попадёт в заявку для администраторов конкурса."""

NASSAL_CATEGORY_INTRO_TEXT = """🎼 <b>Супер, аватар получен.</b>

<b>Шаг 4 из 5.</b>
Теперь выбери корзину и отправь <b>число от 1 до 4</b>.

Ниже я покажу все корзины конкурса вместе с маскотами сезона."""

NASSAL_CONFIRM_TEXT = """📋 <b>Проверь, пожалуйста, заявку на NASSAL2026</b>

<b>Участник(и):</b> {participants}
<b>Smule nick:</b> {smule_nick}
<b>Корзина:</b> {basket_name} — {basket_role}

Если всё верно, ответь <b>да</b>.
Если нужно заполнить заново, ответь <b>нет</b>."""

NASSAL_SUCCESS_TEXT = """🎉 <b>Поздравляем!</b>

Вы успешно зарегистрированы на <b>NASSAL2026</b> — <b>National Artist Singing Smule Award League 2026</b>.

Заявка уже отправлена администраторам конкурса.
Переходите в официальный чат участников по ссылке ниже:"""


def get_basket_caption(choice: str) -> str:
    basket = NASSAL_BASKETS[choice]
    return f"<b>{choice}. {basket['name']}</b>\n{basket['role']}"


def get_basket_full_name(choice: str) -> str:
    basket = NASSAL_BASKETS[choice]
    return f"{basket['name']} — {basket['role']}"


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


async def send_category_guide(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Отправляет описание корзин с иконками маскотов."""
    await context.bot.send_message(
        chat_id=chat_id,
        text=NASSAL_CATEGORY_INTRO_TEXT,
        parse_mode='HTML',
    )

    for choice in ("1", "2", "3", "4"):
        basket = NASSAL_BASKETS[choice]
        photo = build_binary_stream(basket["image_path"])
        caption = get_basket_caption(choice)
        if photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode='HTML',
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode='HTML',
            )

    await context.bot.send_message(
        chat_id=chat_id,
        text="Отправь одним сообщением число <b>1</b>, <b>2</b>, <b>3</b> или <b>4</b>.",
        parse_mode='HTML',
    )


async def send_registration_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int, registration: dict):
    """Показывает пользователю собранные данные перед подтверждением."""
    basket_choice = registration["category_choice"]
    basket = NASSAL_BASKETS[basket_choice]
    summary = NASSAL_CONFIRM_TEXT.format(
        participants=registration["participants"],
        smule_nick=registration["smule_nick"],
        basket_name=basket["name"],
        basket_role=basket["role"],
    )

    avatar_file_id = registration.get("avatar_file_id")
    if avatar_file_id:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=avatar_file_id,
            caption=summary,
            parse_mode='HTML',
        )
    else:
        photo = build_binary_stream(basket["image_path"])
        if photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=summary,
                parse_mode='HTML',
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=summary,
                parse_mode='HTML',
            )


async def send_success_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Отправляет финальное поздравление и ссылку на чат конкурса."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Перейти в чат NASSAL2026", url=NASSAL_JOIN_URL)]
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text=NASSAL_SUCCESS_TEXT,
        parse_mode='HTML',
        reply_markup=keyboard,
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

    user_states[user_id] = NASSAL_NAMES_STATE
    context.user_data.pop("nassal_registration", None)

    reply_to_message_id = msg.message_id if msg else None
    await send_nassal_intro(context, chat.id, reply_to_message_id=reply_to_message_id)


async def nassal2026_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда запуска регистрации на конкурс NASSAL2026."""
    await start_nassal_registration(update, context)
