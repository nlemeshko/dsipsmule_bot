"""Route whole-word group shortcuts to existing command handlers."""

import re
from copy import copy
from types import SimpleNamespace

from commands.entertainment import cat_command, casino_command, meme_command, random_command
from commands.hall import halllist_command
from commands.prediction import prediction_command
from commands.roast_proof import proof_command, roast_command

WORD_COMMANDS = {
    "котик": cat_command,
    "судьба": prediction_command,
    "песня": random_command,
    "мем": meme_command,
    "казино": casino_command,
    "бурмалда": casino_command,
    "слава": halllist_command,
    "пруф": proof_command,
    "лох": roast_command,
}
WORD_PATTERN = re.compile(r"\b(" + "|".join(WORD_COMMANDS) + r")\b", re.IGNORECASE)
DRAW_PATTERN = re.compile(r"\bнарисуй\b", re.IGNORECASE)


def match_word_command(text):
    drawing = DRAW_PATTERN.search(text)
    if drawing:
        return "нарисуй", text[drawing.end():].lstrip(" \t\r\n,:—-")
    match = WORD_PATTERN.search(text)
    return (match.group().lower(), "") if match else None


class ReplyMessage:
    """Make all shortcut output a reply, preserving explicit roast/proof targets."""

    def __init__(self, message):
        self.original = message

    def __getattr__(self, name):
        return getattr(self.original, name)

    async def reply_text(self, *args, **kwargs):
        kwargs.setdefault("reply_to_message_id", self.original.message_id)
        return await self.original.reply_text(*args, **kwargs)

    async def reply_photo(self, *args, **kwargs):
        kwargs.setdefault("reply_to_message_id", self.original.message_id)
        return await self.original.reply_photo(*args, **kwargs)


class CommandUpdate:
    """Supply legacy commands with the real chat sender instead of Telegram's placeholder."""

    def __init__(self, update):
        self.original = update
        self.message = self.effective_message = ReplyMessage(update.message)
        self.effective_user = update.effective_user
        sender = update.message.sender_chat
        if sender:
            self.effective_user = SimpleNamespace(
                id=sender.id, first_name=getattr(sender, "title", None) or "Участник",
                username=getattr(sender, "username", None), is_bot=False,
            )

    def __getattr__(self, name):
        return getattr(self.original, name)


async def run_word_command(update, context, match):
    word, description = match
    command_context = copy(context)
    command_context.args = [description] if description else []
    command_update = CommandUpdate(update)
    if word == "нарисуй":
        from commands.ai import draw_command
        await draw_command(command_update, command_context)
    else:
        await WORD_COMMANDS[word](command_update, command_context)
