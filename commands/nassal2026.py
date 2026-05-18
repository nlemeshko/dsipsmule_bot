#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регистрация на вокальный конкурс NASSAL2026.
"""

import asyncio
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from commands.callback_handler import (
    user_states,
    NASSAL_NAMES_STATE,
    NASSAL_FIRST_STAGE_LINK_STATE,
)
from commands.common import build_binary_stream
from storage.s3_registry import find_final_registration_by_user_id, find_registration_by_user_id


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

<b>Шаг 1 из 4.</b>
Напиши <b>одно или два имени участников</b>.

Если это сольная заявка — укажи одно имя.
Если это дуэт — укажи два имени одним сообщением."""

NASSAL_AVATAR_TEXT = """🖼️ <b>Принято.</b>

<b>Шаг 2 из 4.</b>
Теперь пришли <b>аватар</b> участника или дуэта одной фотографией.

Это изображение попадёт в заявку для администраторов конкурса."""

NASSAL_CATEGORY_INTRO_TEXT = """🎼 <b>Супер, аватар получен.</b>

<b>Шаг 3 из 4.</b>
Теперь выбери корзину и отправь <b>число от 1 до 4</b>.

Ниже собраны все корзины конкурса и маскоты сезона.

<i>Выбирай корзину с умом: ориентируйся на свой стиль, подачу и настроение номера.</i>"""

NASSAL_CONFIRM_TEXT = """📋 <b>Проверь, пожалуйста, заявку на NASSAL2026</b>

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {basket_name} — {basket_role}

Если всё верно, ответь <b>да</b>.
Если нужно заполнить заново, ответь <b>нет</b>."""

NASSAL_SUCCESS_TEXT = """🎉 <b>Поздравляем!</b>

Вы успешно зарегистрированы на <b>NASSAL2026</b> — <b>National Artist Singing Smule Award League 2026</b>.

Заявка уже отправлена администраторам конкурса.
Переходите в официальный чат участников по ссылке ниже:"""

NASSAL_ALREADY_REGISTERED_TEXT = """✅ <b>Ты уже зарегистрирован(а) на NASSAL2026</b>

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {category_name}

Если хочешь, можешь посмотреть текущее состояние корзин или удалить свою регистрацию."""

NASSAL_FIRST_STAGE_FOUND_TEXT = """📝 <b>Этап I</b>

Мы нашли твою регистрацию на конкурс.

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {category_name}

Теперь можешь присылать <b>ссылки, фото и аудио</b> хоть несколькими сообщениями.

Когда всё отправишь, напиши <b>готово</b>."""

NASSAL_FIRST_STAGE_NOT_FOUND_TEXT = """⚠️ <b>Этап I</b>

Мы не нашли твою регистрацию в списке конкурса.

Если что-то сломалось и тебя не удалось найти, всё равно можешь отправить <b>ссылки, фото и аудио</b> несколькими сообщениями.
Когда закончишь, напиши <b>готово</b>.
Мы сохраним её отдельно и передадим администраторам."""

NASSAL_FIRST_STAGE_SUCCESS_TEXT = """✅ <b>Спасибо!</b>

Твоя работа для <b>Этапа I</b> принята и передана администраторам."""

NASSAL_FIRST_STAGE_ALREADY_EXISTS_TEXT = """📝 <b>Этап I</b>

Твоя работа уже сохранена.

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {category_name}
<b>Материал:</b> {work_label}
{work_text_block}

Если хочешь отправить новую работу, сначала удали текущую."""

NASSAL_FINAL_FOUND_TEXT = """🏆 <b>Финал</b>

Мы нашли тебя в списке финалистов.

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {category_name}

<b>ТЕМА ФИНАЛА</b>
{final_topic}

Теперь можешь присылать <b>ссылки, фото и аудио</b> хоть несколькими сообщениями.

Когда всё отправишь, напиши <b>готово</b>."""

NASSAL_FINAL_NOT_FOUND_TEXT = """⚠️ <b>Финал</b>

Мы не нашли тебя в списке финалистов.

Доступ к этой кнопке должен открываться только тем, кто есть в финальном реестре.
Если это ошибка, напиши администраторам."""

NASSAL_FINAL_SUCCESS_TEXT = """✅ <b>Спасибо!</b>

Твоя работа для <b>Финала</b> принята и передана администраторам."""

NASSAL_FINAL_ALREADY_EXISTS_TEXT = """🏆 <b>Финал</b>

Твоя работа уже сохранена.

<b>Участник(и):</b> {participants}
<b>Корзина:</b> {category_name}
<b>Материал:</b> {work_label}
{work_text_block}

Если хочешь отправить новую работу, сначала удали текущую."""

NASSAL_FINAL_TOPICS = {
    "1": "1. Лучшее - Исполнить свою лучшую композицию максимально наполнив ее музыкальными фишками",
    "2": "2. Металл - Дать максимального рока в этой дыре - исполнить лучшее рок произведение которые Вы можете",
    "3": "3. Дисс - (Все понятно написать дисс на любого из участвующих конкурентов или на всех или на организаторов)",
    "4": "4. Смешное - (Сделать самое смешное исполнение любой песни или придумать свою чтобы рассмешить всех)",
}


def build_baskets_status_text(registrations: list[dict]) -> str:
    """Собирает сводку по корзинам и зарегистрированным участникам."""
    basket_lines = ["<b>📊 Текущее состояние корзин</b>", ""]

    for choice in ("1", "2", "3", "4"):
        basket = NASSAL_BASKETS[choice]
        basket_rows = [
            row for row in registrations
            if str(row.get("category_code", "")).strip() == choice
        ]
        participants = [
            escape((row.get("participants") or "").strip())
            for row in basket_rows
            if (row.get("participants") or "").strip()
        ]
        participants_text = ", ".join(participants) if participants else "пока никого"
        basket_lines.append(
            f"<b>{choice}. {escape(basket['name'])}</b> — {len(basket_rows)}\n"
            f"{participants_text}"
        )
        if choice != "4":
            basket_lines.append("")

    return "\n".join(basket_lines)


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


async def send_category_guide(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    registrations: list[dict] | None = None,
):
    """Отправляет текстовое описание корзин без изображений."""
    basket_lines = [
        NASSAL_CATEGORY_INTRO_TEXT,
        "",
        "<b>🎭 Корзины конкурса</b>",
        "",
    ]

    for choice in ("1", "2", "3", "4"):
        basket_lines.append(get_basket_caption(choice))
        basket_lines.append("")

    if registrations is not None:
        basket_lines.append("━━━━━━━━━━━━")
        basket_lines.append("")
        basket_lines.append(build_baskets_status_text(registrations).strip())
        basket_lines.append("")

    basket_lines.append("Отправь одним сообщением <b>1</b>, <b>2</b>, <b>3</b> или <b>4</b>.")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(basket_lines),
        parse_mode='HTML',
    )


async def send_registration_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int, registration: dict):
    """Показывает пользователю собранные данные перед подтверждением."""
    basket_choice = registration["category_choice"]
    basket = NASSAL_BASKETS[basket_choice]
    summary = NASSAL_CONFIRM_TEXT.format(
        participants=registration["participants"],
        basket_name=basket["name"],
        basket_role=basket["role"],
    )
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


async def send_registered_actions(context: ContextTypes.DEFAULT_TYPE, chat_id: int, registration: dict):
    """Показывает меню действий, если пользователь уже зарегистрирован."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Показать состояние корзин", callback_data="nassal_show_status")],
        [InlineKeyboardButton("Удалиться", callback_data="nassal_delete_registration")],
    ])
    text = NASSAL_ALREADY_REGISTERED_TEXT.format(
        participants=escape(registration.get("participants", "Не указано")),
        category_name=escape(registration.get("category_name", "Не указана")),
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard,
    )


async def send_baskets_status_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    registrations: list[dict],
):
    """Отправляет отдельное сообщение с текущим состоянием корзин."""
    text = (
        "<b>🎭 Корзины NASSAL2026</b>\n\n"
        "Выбирай корзину с умом: ориентируйся на свой стиль, подачу и настроение номера.\n\n"
        f"{build_baskets_status_text(registrations)}"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML',
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

    existing_registration = None
    try:
        existing_registration = await asyncio.to_thread(find_registration_by_user_id, user_id)
    except Exception:
        existing_registration = None

    if existing_registration is not None:
        await send_registered_actions(context, chat.id, existing_registration)
        return

    user_states[user_id] = NASSAL_NAMES_STATE
    context.user_data.pop("nassal_registration", None)

    reply_to_message_id = msg.message_id if msg else None
    await send_nassal_intro(context, chat.id, reply_to_message_id=reply_to_message_id)


async def nassal2026_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда запуска регистрации на конкурс NASSAL2026."""
    await start_nassal_registration(update, context)


async def start_first_stage_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает отправку работы для Этапа I."""
    await start_stage_submission(update, context, stage_kind="first_stage")


async def start_final_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает отправку работы для финала."""
    await start_stage_submission(update, context, stage_kind="final")


async def start_stage_submission(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stage_kind: str = "first_stage",
):
    """Запускает отправку работы для выбранного этапа."""
    user_id = update.effective_user.id
    chat = update.effective_chat
    msg = update.effective_message
    stage_label = "Финала" if stage_kind == "final" else "Этапа I"

    if not chat or chat.type != "private":
        await msg.reply_text(f"Отправка работы для {stage_label} доступна только в личных сообщениях с ботом.")
        return

    registration = None
    try:
        finder = find_final_registration_by_user_id if stage_kind == "final" else find_registration_by_user_id
        registration = await asyncio.to_thread(finder, user_id)
    except Exception:
        registration = None

    if stage_kind == "final" and registration is None:
        await context.bot.send_message(
            chat_id=chat.id,
            text=NASSAL_FINAL_NOT_FOUND_TEXT,
            parse_mode="HTML",
        )
        return

    from storage.s3_registry import find_final_submission_by_user_id, find_first_stage_submission_by_user_id

    existing_submission = None
    try:
        submission_finder = find_final_submission_by_user_id if stage_kind == "final" else find_first_stage_submission_by_user_id
        existing_submission = await asyncio.to_thread(submission_finder, user_id)
    except Exception:
        existing_submission = None

    if existing_submission is not None:
        _, submission = existing_submission
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Удалить работу", callback_data="nassal_final_delete" if stage_kind == "final" else "nassal_first_stage_delete")]
        ])
        work_type = (submission.get("work_type") or "").strip()
        work_url = escape(submission.get("work_url", "Не указана"))
        work_text = escape(submission.get("work_text", ""))
        if work_type in {"photo", "voice", "audio"} and work_url != "Не указана":
            work_label = work_url
        elif work_type == "photo":
            work_label = "фото"
        elif work_type == "voice":
            work_label = "голосовое"
        elif work_type == "audio":
            work_label = "аудио"
        else:
            work_label = work_url
        work_text_block = f"<b>Текст:</b> {work_text}" if work_text else "<b>Текст:</b> нет"
        already_exists_text = NASSAL_FINAL_ALREADY_EXISTS_TEXT if stage_kind == "final" else NASSAL_FIRST_STAGE_ALREADY_EXISTS_TEXT
        text = already_exists_text.format(
            participants=escape(submission.get("participants", "Не указано")),
            category_name=escape(submission.get("category_name", "Не указана") or "other"),
            work_label=work_label,
            work_text_block=work_text_block,
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    context.user_data["nassal_first_stage"] = {
        "stage_kind": stage_kind,
        "registration_found": registration is not None,
        "registration": registration,
    }
    user_states[user_id] = NASSAL_FIRST_STAGE_LINK_STATE

    if registration is None:
        await context.bot.send_message(
            chat_id=chat.id,
            text=NASSAL_FIRST_STAGE_NOT_FOUND_TEXT,
            parse_mode="HTML",
        )
        return

    participants = escape(registration.get("participants", "Не указано"))
    category_name = escape(registration.get("category_name", "Не указана"))
    avatar_url = (registration.get("avatar_url") or "").strip()
    caption_template = NASSAL_FINAL_FOUND_TEXT if stage_kind == "final" else NASSAL_FIRST_STAGE_FOUND_TEXT
    final_topic = ""
    if stage_kind == "final":
        final_topic = escape(
            NASSAL_FINAL_TOPICS.get(
                (registration.get("category_code") or "").strip(),
                "Тема не найдена. Напиши администраторам, если это ошибка.",
            )
        )
    caption = caption_template.format(
        participants=participants,
        category_name=category_name,
        final_topic=final_topic,
    )
    if avatar_url:
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=avatar_url,
            caption=caption,
            parse_mode="HTML",
        )
    else:
        await context.bot.send_message(
            chat_id=chat.id,
            text=caption,
            parse_mode="HTML",
        )
