#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команды для зала славы/позора: /hall, /halllist, /vote
"""

import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from commands.common import build_binary_stream
from storage.hall import hall_path, load_hall_data, save_hall_data, update_hall_data

logger = logging.getLogger(__name__)


async def hall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /hall"""
    
    try:
        args = update.message.text.split(maxsplit=2)
        if len(args) < 3:
            await update.message.reply_text("Использование: /hall [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            await update.message.reply_text("Категория должна быть 'legend' или 'cringe'")
            return
        
        nominee = args[2]
        nominator = update.effective_user.username or f"id{update.effective_user.id}"
        
        def nominate(rows):
            if any(row['name'] == nominee and row['category'] == category for row in rows):
                return False, False
            rows.append({"category": category, "name": nominee, "nominated_by": nominator,
                         "date": datetime.now().strftime("%Y-%m-%d"), "votes": '1'})
            return True, True

        if not await asyncio.to_thread(update_hall_data, nominate):
            await update.message.reply_text(f"@{nominee} уже номинирован в эту категорию!")
            return

        category_emoji = "🏆" if category == "legend" else "🤦"
        response_text = (
            f"{category_emoji} Новая номинация!\n"
            f"Категория: {'Легенда' if category == 'legend' else 'Кринж'}\n"
            f"Номинант: {nominee}\n"
            f"Номинировал: {nominator}"
        )

        # Добавляем отправку картинки
        image_path = 'images/hall.png'
        photo = build_binary_stream(image_path)
        if photo:
            await update.message.reply_photo(
                photo,
                caption=response_text
            )
            print(f"Картинка {image_path} отправлена как ответ для команды /hall.")
        else:
            print(f"Файл картинки {image_path} не найден для команды /hall. Отправляю только текст как ответ.")
            await update.message.reply_text(response_text)

        print(f"Номинация создана: {response_text}")
        
    except Exception as e:
        logger.error("Hall nomination failed: %s", type(e).__name__)
        await update.message.reply_text("Не удалось сохранить номинацию. Попробуйте позже.")

async def halllist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /halllist"""
    
    try:
        print(f"Команда /halllist от {update.effective_user.username or update.effective_user.id}")
        
        hall_data = await asyncio.to_thread(load_hall_data)
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
        photo = build_binary_stream(image_path)
        if photo:
            await update.message.reply_photo(photo, caption=response_text)
            print(f"Картинка {image_path} отправлена для команды /halllist.")
        else:
            print(f"Файл картинки {image_path} не найден для команды /halllist. Отправляю только текст.")
            await update.message.reply_text(response_text)
        
        print(f"Список зала славы/позора отправлен: {response_text}")
        
    except Exception as e:
        logger.error("Hall listing failed: %s", type(e).__name__)
        await update.message.reply_text("Не удалось загрузить зал славы. Попробуйте позже.")

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /vote"""
    
    try:
        args = update.message.text.split(maxsplit=2)
        if len(args) < 3:
            await update.message.reply_text("Использование: /vote [legend/cringe] [имя пользователя]")
            return
        
        category = args[1].lower()
        if category not in ['legend', 'cringe']:
            await update.message.reply_text("Категория должна быть 'legend' или 'cringe'")
            return
        
        nominee = args[2]
        def vote(rows):
            for row in rows:
                if row['name'] == nominee and row['category'] == category:
                    row['votes'] = str(int(row['votes']) + 1)
                    return True, True
            return False, False

        if not await asyncio.to_thread(update_hall_data, vote):
            await update.message.reply_text(f"Номинация для @{nominee} в категории {category} не найдена!")
            return

        category_emoji = "🏆" if category == "legend" else "🤦"
        response_text = f"{category_emoji} Ваш голос за @{nominee} учтен!"

        # Добавляем отправку картинки
        image_path = 'images/vote.png'
        photo = build_binary_stream(image_path)
        if photo:
            await update.message.reply_photo(photo, caption=response_text)
            print(f"Картинка {image_path} отправлена для команды /vote.")
        else:
            print(f"Файл картинки {image_path} не найден для команды /vote. Отправляю только текст.")
            await update.message.reply_text(response_text)

    except Exception as e:
        logger.error("Hall vote failed: %s", type(e).__name__)
        await update.message.reply_text("Не удалось сохранить голос. Попробуйте позже.")
