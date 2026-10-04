"""Open the club Mini App, with a compact fallback menu."""

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

SITE_URL = "https://dsipsmule.one"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app_url = os.getenv("MINI_APP_URL", "").strip()
    private = update.effective_chat.type == "private"
    if app_url and private:
        rows = [[InlineKeyboardButton("Открыть приложение Ведьмака ↗", web_app=WebAppInfo(app_url))]]
        text = (
            "🗡️ Ведьмак на связи. Добро пожаловать в DSIP Smule!\n\n"
            "Анонимки, песни, оценки, промо, игры, голосовой Геральт и зал славы — "
            "всё в одном приложении.\n\nНажми кнопку ниже или «Открыть приложение» в меню бота."
        )
    elif private:
        rows = [
            [InlineKeyboardButton("🕵 Анонимка", callback_data="button1"), InlineKeyboardButton("🎶 Песня", callback_data="button2")],
            [InlineKeyboardButton("🎧 Оценить", callback_data="button3"), InlineKeyboardButton("🎲 Песня дня", callback_data="button4")],
            [InlineKeyboardButton("📢 Промо", callback_data="button6")],
        ]
        text = "🗡️ Ведьмак · DSIP Smule\n\nВыбери контракт ниже. Игры, голосовой Геральт и остальные команды — в /help."
    else:
        rows = [[InlineKeyboardButton("Открыть бота ↗", url=f"https://t.me/{context.bot.username}?start=app")]]
        text = "🗡️ Ведьмак на связи. Открой личный чат с ботом, чтобы запустить приложение DSIP Smule. Команды и игры доступны и здесь."
    rows.append([InlineKeyboardButton("Официальный сайт · dsipsmule.one ↗", url=SITE_URL)])
    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))
