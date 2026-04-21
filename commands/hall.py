#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команды для зала славы/позора: /hall, /halllist, /vote
"""

import csv
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from commands.common import build_binary_stream

# Загрузка данных зала славы/позора
def load_hall_data():
    try:
        with open('data/hall.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except FileNotFoundError:
        return []

# Сохранение данных зала славы/позора
def save_hall_data(data):
    with open('data/hall.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['category', 'name', 'nominated_by', 'date', 'votes'])
        writer.writeheader()
        writer.writerows(data)

async def hall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /hall"""
    hall_data = load_hall_data()
    
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
        
        # Проверяем, не номинирован ли уже этот пользователь
        for row in hall_data:
            if row['name'] == nominee and row['category'] == category:
                await update.message.reply_text(f"@{nominee} уже номинирован в эту категорию!")
                return
        
        # Добавляем новую номинацию
        new_nomination = {
            "category": category,
            "name": nominee,
            "nominated_by": nominator,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "votes": '1'
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
        print(f"Ошибка в команде /hall: {e}")
        await update.message.reply_text(f"Произошла ошибка при обработке команды: {e}")

async def halllist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /halllist"""
    hall_data = load_hall_data()
    
    try:
        print(f"Команда /halllist от {update.effective_user.username or update.effective_user.id}")
        
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
        print(f"Ошибка в команде /halllist: {e}")
        await update.message.reply_text(f"Произошла ошибка при получении списка: {e}")

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /vote"""
    hall_data = load_hall_data()
    
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
        # Ищем номинацию
        found = False
        for row in hall_data:
            if row['name'] == nominee and row['category'] == category:
                row['votes'] = str(int(row['votes']) + 1)
                found = True
                break
        
        if not found:
            await update.message.reply_text(f"Номинация для @{nominee} в категории {category} не найдена!")
            return
        
        # Сохраняем обновленные данные
        save_hall_data(hall_data)
        
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
        print(f"Ошибка в команде /vote: {e}")
        await update.message.reply_text(f"Произошла ошибка при голосовании: {e}")
