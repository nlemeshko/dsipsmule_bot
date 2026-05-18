#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик FSM состояний для анонимок, песен, оценок и промо
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

# Импорт состояний из callback_handler
from commands.callback_handler import (
    user_states,
    ANON_STATE,
    SONG_STATE,
    RATE_LINK_STATE,
    PROMOTE_STATE,
    NASSAL_NAMES_STATE,
    NASSAL_AVATAR_STATE,
    NASSAL_CATEGORY_STATE,
    NASSAL_CONFIRM_STATE,
    NASSAL_FIRST_STAGE_LINK_STATE,
    NASSAL_FIRST_STAGE_TEXT_CONFIRM_STATE,
    NASSAL_FIRST_STAGE_TEXT_STATE,
)

# Импорт функций отправки админам
from commands.admin_notifications import (
    send_moderation_request,
    send_anon_with_photo,
    send_anon_with_voice,
    send_photo_to_admins,
    send_photo_url_to_admins,
    send_voice_to_admins,
    send_audio_to_admins,
    send_to_admins,
)
from commands.nassal2026 import (
    NASSAL_BASKETS,
    NASSAL_AVATAR_TEXT,
    YES_ANSWERS,
    NO_ANSWERS,
    get_basket_full_name,
    send_category_guide,
    send_registration_summary,
    send_success_message,
    NASSAL_FINAL_SUCCESS_TEXT,
    NASSAL_FIRST_STAGE_SUCCESS_TEXT,
)
from storage.s3_registry import (
    append_registration_row,
    append_first_stage_submission_row,
    build_registration_row,
    build_first_stage_submission_row,
    get_final_storage_key,
    get_first_stage_storage_key,
    load_registration_rows,
    registration_exists,
    _normalize_participants,
    upload_avatar_bytes,
    upload_final_file_bytes,
    upload_first_stage_file_bytes,
)


logger = logging.getLogger(__name__)


FIRST_STAGE_ADMIN_TEXT_LIMIT = 700
NASSAL_FIRST_STAGE_DONE_ANSWERS = {"готово", "done", "finish", "стоп"}
NASSAL_FIRST_STAGE_CONTINUE_TEXT = (
    "Материал добавлен.\n\n"
    "Можешь прислать ещё <b>ссылку, фото или аудио</b>.\n"
    "Когда всё отправишь, напиши <b>готово</b>."
)
NASSAL_FIRST_STAGE_TEXT_QUESTION = (
    "Все материалы получил.\n\n"
    "Есть ли <b>текст</b> к этой работе?\n"
    "Ответьте, пожалуйста, <b>да</b> или <b>нет</b>."
)
NASSAL_FINAL_CONTINUE_TEXT = (
    "Материал добавлен.\n\n"
    "Можешь прислать ещё <b>ссылку, фото или аудио</b> для <b>Финала</b>.\n"
    "Когда всё отправишь, напиши <b>готово</b>."
)


def _get_stage_kind(context: ContextTypes.DEFAULT_TYPE) -> str:
    first_stage_data = context.user_data.get("nassal_first_stage", {})
    return first_stage_data.get("stage_kind", "first_stage")


def _get_stage_label(context: ContextTypes.DEFAULT_TYPE) -> str:
    return "Финала" if _get_stage_kind(context) == "final" else "Этапа II"


def _get_stage_continue_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return NASSAL_FINAL_CONTINUE_TEXT if _get_stage_kind(context) == "final" else NASSAL_FIRST_STAGE_CONTINUE_TEXT


def _get_stage_success_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return NASSAL_FINAL_SUCCESS_TEXT if _get_stage_kind(context) == "final" else NASSAL_FIRST_STAGE_SUCCESS_TEXT


def _get_first_stage_materials(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    first_stage_data = context.user_data.setdefault("nassal_first_stage", {})
    materials = first_stage_data.get("materials")
    if isinstance(materials, list):
        return materials

    legacy_work_type = (first_stage_data.get("work_type") or "").strip()
    legacy_work_url = (first_stage_data.get("work_url") or "").strip()
    legacy_work_file_id = (first_stage_data.get("work_file_id") or "").strip()
    materials = []
    if legacy_work_type or legacy_work_url or legacy_work_file_id:
        materials.append({
            "type": legacy_work_type or ("link" if legacy_work_url else "unknown"),
            "url": legacy_work_url,
            "file_id": legacy_work_file_id,
        })
    first_stage_data["materials"] = materials
    return materials


def _get_first_stage_material_slot(work_type: str) -> str:
    normalized_type = (work_type or "").strip()
    if normalized_type in {"voice", "audio"}:
        return "audio"
    return normalized_type


def _has_first_stage_material_type(materials: list[dict], work_type: str) -> bool:
    material_slot = _get_first_stage_material_slot(work_type)
    return any(_get_first_stage_material_slot(item.get("type", "")) == material_slot for item in materials)


def _append_first_stage_material(
    context: ContextTypes.DEFAULT_TYPE,
    work_type: str,
    work_url: str = "",
    work_file_id: str = "",
) -> bool:
    materials = _get_first_stage_materials(context)
    if _has_first_stage_material_type(materials, work_type):
        return False

    materials.append({
        "type": (work_type or "").strip(),
        "url": (work_url or "").strip(),
        "file_id": (work_file_id or "").strip(),
    })
    first_stage_data = context.user_data.setdefault("nassal_first_stage", {})
    first_stage_data["materials"] = materials
    first_stage_data["work_type"] = "|".join(item["type"] for item in materials if item.get("type"))
    first_stage_data["work_url"] = "\n".join(item["url"] for item in materials if item.get("url"))
    first_stage_data["work_file_id"] = "\n".join(item["file_id"] for item in materials if item.get("file_id"))
    first_stage_data.pop("work_text", None)
    return True


def _format_materials_for_message(materials: list[dict]) -> str:
    lines = []
    for index, material in enumerate(materials, start=1):
        material_type = material.get("type", "")
        label = {
            "link": "ссылка",
            "photo": "фото",
            "voice": "голосовое",
            "audio": "аудио",
        }.get(material_type, material_type or "материал")
        value = material.get("url", "").strip() or "медиафайл"
        lines.append(f"{index}. {label}: {value}")
    return "\n".join(lines) if lines else "нет"


def _looks_like_url(value: str) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def _truncate_first_stage_admin_value(value: str, limit: int = FIRST_STAGE_ADMIN_TEXT_LIMIT) -> str:
    normalized = (value or "").strip()
    if len(normalized) <= limit:
        return normalized or "нет"
    return f"{normalized[:limit].rstrip()}... [обрезано]"


def _build_first_stage_admin_message(
    update: Update,
    submission_row: dict,
    registration_found: bool,
    stage_kind: str = "first_stage",
) -> str:
    stage_title = "Финала" if stage_kind == "final" else "Этапа II"
    user_id = update.effective_user.id
    user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
    work_type = submission_row.get("work_type", "").strip()
    work_type_label = work_type or "unknown"
    work_details = _truncate_first_stage_admin_value(
        submission_row.get("work_url", "").strip() or "медиафайл в сообщении"
    )
    text_block = _truncate_first_stage_admin_value(submission_row.get("work_text", "").strip())

    return (
        f"📝 <b>Новая работа для {stage_title} NASSAL2026</b>\n\n"
        f"<b>Telegram:</b> {user_info}\n"
        f"<b>Имя в Telegram:</b> {update.effective_user.full_name or 'Без имени'}\n"
        f"<b>Участник(и):</b> {submission_row['participants']}\n"
        f"<b>Корзина:</b> {submission_row['category_name'] or 'other'}\n"
        f"<b>Найден в реестре:</b> {'да' if registration_found else 'нет'}\n"
        f"<b>Типы материалов:</b> {work_type_label}\n"
        f"<b>Материалы:</b>\n{work_details}\n"
        f"<b>Текст:</b> {text_block}"
    )


async def _save_first_stage_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, msg):
    user_id = update.effective_user.id
    first_stage_data = context.user_data.get("nassal_first_stage", {})
    stage_kind = _get_stage_kind(context)
    stage_label = _get_stage_label(context)
    registration = first_stage_data.get("registration")
    registration_found = bool(first_stage_data.get("registration_found"))

    participants = (
        registration.get("participants")
        if registration_found and registration
        else (update.effective_user.full_name or "Неизвестный участник")
    )
    category_code = registration.get("category_code") if registration else ""
    category_name = registration.get("category_name") if registration else "other"
    storage_key = (
        get_final_storage_key(category_code if registration_found else None)
        if stage_kind == "final"
        else get_first_stage_storage_key(category_code if registration_found else None)
    )
    materials = _get_first_stage_materials(context)
    work_text = first_stage_data.get("work_text", "")

    normalized_materials = []
    for material in materials:
        material_type = (material.get("type") or "").strip()
        material_url = (material.get("url") or "").strip()
        material_file_id = (material.get("file_id") or "").strip()

        if material_type in {"photo", "voice", "audio"} and material_file_id and not material_url:
            try:
                telegram_file = await context.bot.get_file(material_file_id)
                file_bytes = bytes(await telegram_file.download_as_bytearray())
                material_url = await asyncio.to_thread(
                    upload_final_file_bytes if stage_kind == "final" else upload_first_stage_file_bytes,
                    file_bytes,
                    material_type,
                    telegram_file.file_path,
                    getattr(telegram_file, "mime_type", None),
                )
            except Exception as exc:
                logger.exception("Не удалось загрузить файл %s в Object Storage: %s", stage_label, exc)
        normalized_materials.append({
            "type": material_type,
            "url": material_url,
            "file_id": material_file_id,
        })

    if not normalized_materials:
        await msg.reply_text("Сначала пришлите хотя бы один материал, а потом напишите <b>готово</b>.", parse_mode='HTML')
        return

    first_stage_data["materials"] = normalized_materials
    work_type = "|".join(item["type"] for item in normalized_materials if item.get("type"))
    work_url = _format_materials_for_message(normalized_materials)
    work_file_id = "\n".join(item["file_id"] for item in normalized_materials if item.get("file_id"))
    first_stage_data["work_type"] = work_type
    first_stage_data["work_url"] = work_url
    first_stage_data["work_file_id"] = work_file_id

    submission_row = build_first_stage_submission_row(
        user_id=user_id,
        username=update.effective_user.username,
        full_name=update.effective_user.full_name,
        participants=participants,
        category_code=category_code if registration_found else "",
        category_name=category_name if registration_found else "other",
        work_type=work_type,
        work_url=work_url,
        work_file_id=work_file_id,
        work_text=work_text,
    )
    admin_message = _build_first_stage_admin_message(update, submission_row, registration_found, stage_kind=stage_kind)

    try:
        if registration_found and registration and (registration.get("avatar_url") or "").strip():
            await send_photo_url_to_admins(
                context,
                registration["avatar_url"].strip(),
                admin_message,
            )
        else:
            await send_to_admins(context, admin_message)

        for material in normalized_materials:
            material_type = material.get("type", "")
            material_url = material.get("url", "")
            material_file_id = material.get("file_id", "")
            if material_type == "photo" and material_file_id:
                await send_photo_to_admins(context, material_file_id, material_url or f"Фото для {stage_label}")
            elif material_type == "voice" and material_file_id:
                await send_voice_to_admins(context, material_file_id, material_url or f"Голосовое для {stage_label}")
            elif material_type == "audio" and material_file_id:
                await send_audio_to_admins(context, material_file_id, material_url or f"Аудио для {stage_label}")

        await asyncio.to_thread(
            append_first_stage_submission_row,
            storage_key,
            submission_row,
        )
    except Exception as exc:
        logger.exception("Не удалось сохранить работу %s: %s", stage_label, exc)
        await msg.reply_text(
            f"Не удалось сохранить работу для {stage_label}.\n\nПожалуйста, попробуйте отправить материал ещё раз чуть позже."
        )
        return

    await msg.reply_text(_get_stage_success_text(context), parse_mode='HTML')
    context.user_data.pop("nassal_first_stage", None)
    user_states.pop(user_id, None)

async def handle_fsm_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик FSM состояний"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    # Проверяем, что это личное сообщение
    if chat_type != "private":
        return
    
    # FSM: если пользователь пишет анонимку
    if user_states.get(user_id) == ANON_STATE:
        print(f"Пользователь {user_id} в ANON_STATE. Проверка типа сообщения.")
        if msg and msg.text:
            # Обработка текстовых сообщений
            text = msg.text.strip()
            anon_text = f"{text}\n\n#анон"
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "анонимка", user_info, anon_text)
            print(f"Новая анонимка на модерацию от {user_info}:\n{anon_text}")
            await msg.reply_text("Спасибо! Ваша анонимка отправлена на модерацию.")
            user_states.pop(user_id, None)
            return

    elif user_states.get(user_id) == NASSAL_NAMES_STATE:
        participants = _normalize_participants(msg.text if (msg and msg.text) else "")
        if not participants:
            await msg.reply_text("Пожалуйста, напишите одно имя или два имени участников текстом.")
            return

        context.user_data["nassal_registration"] = {
            "participants": participants,
        }
        user_states[user_id] = NASSAL_AVATAR_STATE
        await msg.reply_text(NASSAL_AVATAR_TEXT, parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_AVATAR_STATE:
        await msg.reply_text("Сейчас нужен аватар. Пришлите его одной фотографией.")
        return

    elif user_states.get(user_id) == NASSAL_CATEGORY_STATE:
        category_choice = msg.text.strip() if (msg and msg.text) else ""
        if category_choice not in NASSAL_BASKETS:
            await msg.reply_text(
                "Нужно отправить одно число: 1, 2, 3 или 4.\n\n"
                "1 — Корзина имени Гены Букина — Вокалисты\n"
                "2 — Корзина имени Светы Букиной — Рокеры\n"
                "3 — Корзина имени Ромы Букина — Реперы\n"
                "4 — Корзина имени Даши Букиной — Приколисты"
            )
            return

        registration = context.user_data.get("nassal_registration", {})
        registration["category_choice"] = category_choice
        user_states[user_id] = NASSAL_CONFIRM_STATE
        await send_registration_summary(context, msg.chat_id, registration)
        return

    elif user_states.get(user_id) == NASSAL_CONFIRM_STATE:
        answer = msg.text.strip().lower() if (msg and msg.text) else ""

        if answer in YES_ANSWERS:
            registration = context.user_data.get("nassal_registration", {})
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            full_name = update.effective_user.full_name or "Без имени"
            category_choice = registration["category_choice"]
            basket_full_name = get_basket_full_name(category_choice)
            admin_message = (
                "🏆 <b>Новая регистрация на конкурс NASSAL2026</b>\n\n"
                f"<b>Telegram:</b> {user_info}\n"
                f"<b>Имя в Telegram:</b> {full_name}\n"
                f"<b>Участник(и):</b> {registration['participants']}\n"
                f"<b>Корзина:</b> {basket_full_name}"
            )

            avatar_file_id = registration.get("avatar_file_id")
            if avatar_file_id:
                await send_photo_to_admins(context, avatar_file_id, admin_message)
            else:
                await send_to_admins(context, admin_message)

            avatar_url = None
            if avatar_file_id:
                try:
                    avatar = await context.bot.get_file(avatar_file_id)
                    avatar_bytes = bytes(await avatar.download_as_bytearray())
                    avatar_url = await asyncio.to_thread(
                        upload_avatar_bytes,
                        avatar_bytes,
                        avatar.file_path,
                    )
                except Exception as exc:
                    logger.exception("Не удалось загрузить аватар в Object Storage: %s", exc)

            s3_row = build_registration_row(
                user_id=user_id,
                username=update.effective_user.username,
                full_name=update.effective_user.full_name,
                participants=registration["participants"],
                category_code=category_choice,
                category_name=basket_full_name,
                avatar_url=avatar_url,
            )
            registration_saved = False
            try:
                await asyncio.to_thread(append_registration_row, s3_row)
                registration_saved = await asyncio.to_thread(
                    registration_exists,
                    user_id,
                    registration["participants"],
                    category_choice,
                )
            except Exception as exc:
                logger.exception("Не удалось сохранить регистрацию в Object Storage: %s", exc)

            if not registration_saved:
                await msg.reply_text(
                    "Не удалось надёжно сохранить регистрацию в конкурсе.\n\n"
                    "Пожалуйста, попробуйте отправить подтверждение ещё раз чуть позже."
                )
                return

            await send_success_message(context, msg.chat_id)
            context.user_data.pop("nassal_registration", None)
            user_states.pop(user_id, None)
            return

        if answer in NO_ANSWERS:
            context.user_data.pop("nassal_registration", None)
            user_states[user_id] = NASSAL_NAMES_STATE
            await msg.reply_text(
                "Хорошо, давай заполним заявку заново.\n\n"
                "Напиши одно имя или два имени участников для регистрации на NASSAL2026."
            )
            return

        await msg.reply_text("Ответьте, пожалуйста, <b>да</b> или <b>нет</b>.", parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_FIRST_STAGE_LINK_STATE:
        work_url = msg.text.strip() if (msg and msg.text) else ""
        materials = _get_first_stage_materials(context)
        if not work_url:
            await msg.reply_text("Пришлите, пожалуйста, ссылку, фото или аудио. Когда закончите, напишите <b>готово</b>.", parse_mode='HTML')
            return
        if work_url.lower() in NASSAL_FIRST_STAGE_DONE_ANSWERS:
            if not materials:
                await msg.reply_text("Пока нет ни одного материала. Сначала пришлите ссылку, фото или аудио.", parse_mode='HTML')
                return
            user_states[user_id] = NASSAL_FIRST_STAGE_TEXT_CONFIRM_STATE
            await msg.reply_text(NASSAL_FIRST_STAGE_TEXT_QUESTION, parse_mode='HTML')
            return

        if not _append_first_stage_material(context, "link", work_url=work_url):
            await msg.reply_text(
                f"Ссылка уже добавлена. Для {_get_stage_label(context)} можно отправить только <b>одну ссылку</b>, одно <b>фото</b> и одно <b>аудио</b>.\n\n"
                "Если всё готово, напиши <b>готово</b>.",
                parse_mode='HTML',
            )
            return
        if not materials and _looks_like_url(work_url):
            user_states[user_id] = NASSAL_FIRST_STAGE_TEXT_CONFIRM_STATE
            await msg.reply_text(NASSAL_FIRST_STAGE_TEXT_QUESTION, parse_mode='HTML')
            return
        await msg.reply_text(_get_stage_continue_text(context), parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_FIRST_STAGE_TEXT_CONFIRM_STATE:
        answer = msg.text.strip().lower() if (msg and msg.text) else ""
        if answer in YES_ANSWERS:
            user_states[user_id] = NASSAL_FIRST_STAGE_TEXT_STATE
            await msg.reply_text("Пришлите текст к работе одним сообщением.", parse_mode='HTML')
            return
        if answer in NO_ANSWERS:
            await _save_first_stage_submission(update, context, msg)
            return

        await msg.reply_text("Ответьте, пожалуйста, <b>да</b> или <b>нет</b>.", parse_mode='HTML')
        return

    elif user_states.get(user_id) == NASSAL_FIRST_STAGE_TEXT_STATE:
        work_text = msg.text.strip() if (msg and msg.text) else ""
        if not work_text:
            await msg.reply_text("Пришлите, пожалуйста, текст одним сообщением.")
            return

        first_stage_data = context.user_data.setdefault("nassal_first_stage", {})
        first_stage_data["work_text"] = work_text
        await _save_first_stage_submission(update, context, msg)
        return

    # FSM: если пользователь предлагает песню
    elif user_states.get(user_id) == SONG_STATE:
        print(f"Пользователь {user_id} в SONG_STATE. Обработка сообщения.")
        song_info = msg.text.strip() if (msg and msg.text) else ""
        if song_info:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "песня", user_info, song_info)
            print(f"Новая песня предложена от {user_info}:\n{song_info}")
            await msg.reply_text("Спасибо! Ваша песня отправлена администраторам.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте название или ссылку на песню.")
            return
            
    # FSM: если пользователь отправляет ссылку для оценки
    elif user_states.get(user_id) == RATE_LINK_STATE:
        print(f"Пользователь {user_id} в RATE_LINK_STATE. Обработка сообщения.")
        rate_link = msg.text.strip() if (msg and msg.text) else ""
        if rate_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "оценка", user_info, rate_link)
            print(f"Новая ссылка для оценки от {user_info}:\n{rate_link}")
            await msg.reply_text("Спасибо! Ваша ссылка отправлена администраторам для оценки.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте ссылку на трек для оценки.")
            return
            
    # FSM: если пользователь отправляет ссылку для промо
    elif user_states.get(user_id) == PROMOTE_STATE:
        print(f"Пользователь {user_id} в PROMOTE_STATE. Обработка сообщения.")
        promote_link = msg.text.strip() if (msg and msg.text) else ""
        if promote_link:
            user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
            
            # Отправляем админам на модерацию
            await send_moderation_request(context, "промо", user_info, promote_link)
            print(f"Новый запрос на промо от {user_info}:\n{promote_link}")
            await msg.reply_text("Спасибо! Ваш запрос на промо отправлен на модерацию.")
            user_states.pop(user_id, None)
            return
        else:
            await msg.reply_text("Пожалуйста, отправьте ссылку на трек для промо.")
            return

async def handle_anon_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных фотографий"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == NASSAL_AVATAR_STATE:
        photo_id = (msg.photo[-1].file_id if (msg and msg.photo) else None)
        if not photo_id:
            await msg.reply_text("Не удалось получить фото. Попробуйте отправить аватар ещё раз.")
            return

        registration = context.user_data.setdefault("nassal_registration", {})
        registration["avatar_file_id"] = photo_id
        user_states[user_id] = NASSAL_CATEGORY_STATE
        registrations = None
        try:
            registrations = await asyncio.to_thread(load_registration_rows)
        except Exception as exc:
            logger.exception("Не удалось загрузить регистрации из Object Storage: %s", exc)
        await send_category_guide(context, msg.chat_id, registrations=registrations)
        return

    if user_states.get(user_id) == NASSAL_FIRST_STAGE_LINK_STATE:
        photo_id = (msg.photo[-1].file_id if (msg and msg.photo) else None)
        if not photo_id:
            await msg.reply_text("Не удалось получить фото. Попробуйте отправить работу ещё раз.")
            return

        if not _append_first_stage_material(context, "photo", work_file_id=photo_id):
            await msg.reply_text(
                f"Фото уже добавлено. Для {_get_stage_label(context)} можно отправить только <b>одно фото</b>.\n\n"
                "Если всё готово, напиши <b>готово</b>.",
                parse_mode='HTML',
            )
            return
        caption = (msg.caption or "").strip() if msg else ""
        if caption:
            if not _append_first_stage_material(context, "link", work_url=caption):
                await msg.reply_text(
                    "Фото добавлено, но ссылка из подписи уже не сохранена: ссылка уже есть.\n\n"
                    "Можно оставить так или написать <b>готово</b>.",
                    parse_mode='HTML',
                )
                return
        await msg.reply_text(_get_stage_continue_text(context), parse_mode='HTML')
        return

    if user_states.get(user_id) == ANON_STATE:
        print(f"Получена фотография от {user_id} в ANON_STATE.")
        # Обработка фотографий
        photo_id = (msg.photo[-1].file_id if (msg and msg.photo) else None)  # Берем последнюю (самую большую) версию фото
        caption = (msg.caption or "") if msg else ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            if photo_id:
                await send_anon_with_photo(context, user_info, photo_id, caption)
            print(f"Анонимная фотография от {user_info} успешно отправлена на модерацию")
            await msg.reply_text("Спасибо! Ваша анонимная фотография отправлена на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке фото админам: {e}")
            if msg:
                await msg.reply_text("Произошла ошибка при отправке фотографии. Попробуйте еще раз.")
        user_states.pop(user_id, None)
        return

async def handle_anon_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик анонимных голосовых сообщений"""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message
    
    if chat_type != "private":
        return
        
    if user_states.get(user_id) == ANON_STATE:
        print(f"Получено голосовое сообщение от {user_id} в ANON_STATE.")
        # Обработка голосовых сообщений
        voice_id = msg.voice.file_id if (msg and msg.voice) else None
        caption = (msg.caption or "") if msg else ""
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID{user_id}"
        
        try:
            # Отправляем админам на модерацию
            if voice_id:
                await send_anon_with_voice(context, user_info, voice_id, caption)
            print(f"Анонимное голосовое сообщение от {user_info} успешно отправлено на модерацию")
            await msg.reply_text("Спасибо! Ваше анонимное голосовое сообщение отправлено на модерацию.")
        except Exception as e:
            print(f"Ошибка при отправке голосового сообщения админам: {e}")
            if msg:
                await msg.reply_text("Произошла ошибка при отправке голосового сообщения. Попробуйте еще раз.")
        user_states.pop(user_id, None)

    elif user_states.get(user_id) == NASSAL_FIRST_STAGE_LINK_STATE:
        voice_id = msg.voice.file_id if (msg and msg.voice) else None
        if not voice_id:
            await msg.reply_text("Не удалось получить аудио. Попробуйте отправить работу ещё раз.")
            return

        if not _append_first_stage_material(context, "voice", work_file_id=voice_id):
            await msg.reply_text(
                f"Аудио уже добавлено. Для {_get_stage_label(context)} можно отправить только <b>одно аудио</b> или <b>одно голосовое</b>.\n\n"
                "Если всё готово, напиши <b>готово</b>.",
                parse_mode='HTML',
            )
            return
        caption = (msg.caption or "").strip() if msg else ""
        if caption:
            if not _append_first_stage_material(context, "link", work_url=caption):
                await msg.reply_text(
                    "Аудио добавлено, но ссылка из подписи уже не сохранена: ссылка уже есть.\n\n"
                    "Можно оставить так или написать <b>готово</b>.",
                    parse_mode='HTML',
                )
                return
        await msg.reply_text(_get_stage_continue_text(context), parse_mode='HTML')
        return


async def handle_fsm_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик аудио для FSM состояний."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    msg = update.effective_message

    if chat_type != "private":
        return

    if user_states.get(user_id) != NASSAL_FIRST_STAGE_LINK_STATE:
        return

    audio_id = msg.audio.file_id if (msg and msg.audio) else None
    if not audio_id:
        await msg.reply_text("Не удалось получить аудиофайл. Попробуйте отправить работу ещё раз.")
        return

    if not _append_first_stage_material(context, "audio", work_file_id=audio_id):
        await msg.reply_text(
            f"Аудио уже добавлено. Для {_get_stage_label(context)} можно отправить только <b>одно аудио</b> или <b>одно голосовое</b>.\n\n"
            "Если всё готово, напиши <b>готово</b>.",
            parse_mode='HTML',
        )
        return
    caption = (msg.caption or "").strip() if msg else ""
    if caption:
        if not _append_first_stage_material(context, "link", work_url=caption):
            await msg.reply_text(
                "Аудио добавлено, но ссылка из подписи уже не сохранена: ссылка уже есть.\n\n"
                "Можно оставить так или написать <b>готово</b>.",
                parse_mode='HTML',
            )
            return
    await msg.reply_text(_get_stage_continue_text(context), parse_mode='HTML')
    return
