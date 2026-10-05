"""Route whole-word group shortcuts to existing command handlers."""

import re
from copy import copy
from types import SimpleNamespace

from commands.entertainment import cat_command, casino_command, meme_command, random_command
from commands.hall import halllist_command
from commands.prediction import prediction_command
from commands.roast_proof import proof_command, roast_command
from commands.fun import passport_command, order_command, ded_command, guess_command, mood_command
from commands.titles import verdict_command

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
    "паспорт": passport_command,
    "орден": order_command,
    "дедометр": ded_command,
    "угадай": guess_command,
    "настроение": mood_command,
    "вердикт": verdict_command,
}
WORD_ALIASES = {
    "котик": (
        "котик", "котики", "котика", "котиков", "котику", "котиком", "котике", "коти",
        "кот", "кота", "коту", "котом", "коте", "коты", "котов", "котам", "котами", "котах",
        "кошка", "кошки", "кошку", "кошке", "кошек", "кошкой", "кошечка", "кошечки", "кошечку",
        "котёнок", "котенок", "котёнка", "котенка", "котята", "котят", "котэ", "котейка", "котейку",
        "котяра", "котяру", "киса", "кису", "киска", "киску", "киська", "киську", "кисуля",
        "кисочка", "кисонька", "мяу", "мур", "мурмур",
    ),
    "судьба": (
        "судьба", "судьбу", "судьбы", "судьбе", "судьбой", "предсказание", "предсказания",
        "предскажи", "предскажите", "погадай", "погадайте", "гадание", "гороскоп", "пророчество",
    ),
    "песня": (
        "песня", "песню", "песни", "песней", "песен", "песнями", "песенка", "песенку",
        "музыка", "музыку", "музычка", "музычку", "музло", "трек", "треки", "трека", "треков",
    ),
    "мем": (
        "мем", "мемы", "мема", "мемов", "мемчик", "мемчики", "мемас", "мемасы",
        "мемасик", "мемасики", "прикол", "приколы", "прикольчик", "ржака", "ржач", "угар",
    ),
    "казино": ("казино", "казик", "слоты", "слот", "слотик", "слотики", "джекпот", "рулетка", "рулетку"),
    "бурмалда": ("бурмалда", "бурмалду", "бурмалды", "бурмалде", "бурмалдочка", "бурмалдочку"),
    "слава": ("слава", "славу", "славы", "легенда", "легенду", "легендой", "легенды", "легенд", "позор", "кринж",
              "зал славы", "зал позора", "зал легенд"),
    "пруф": ("пруф", "пруфы", "пруфов", "пруфани", "докажи", "докажите", "доказательство",
             "доказательства", "подтверди", "подтвердите", "подтверждение"),
    "лох": ("лох", "лохи", "лоха", "лохов", "лошара", "лошары", "лошару", "лузер", "лузеры",
            "неудачник", "неудачники", "прожарь", "прожарка", "обосри", "засри"),
    "паспорт": ("паспорт", "паспорт сквада"),
    "орден": ("орден", "награда", "награду"),
    "дедометр": ("дедометр",),
    "угадай": ("угадай песню",),
    "настроение": ("настроение бота", "настрой деда"),
    "вердикт": ("гей", "гея", "гею", "геем", "гее", "геи", "геев", "геям", "геями", "геях",
                "негр", "негра", "негру", "негром", "негре", "негры", "негров", "неграм", "неграми", "неграх"),
}
DRAW_ALIASES = (
    "нарисуй", "нарисуйте", "рисуй", "нарисовать", "изобрази", "изобразите", "намалюй",
    "сгенерируй картинку", "сгенерируй изображение", "создай картинку", "создай изображение",
    "сделай картинку", "сделай изображение",
)
ALIAS_COMMANDS = {alias: word for word, aliases in WORD_ALIASES.items() for alias in aliases}


def alias_pattern(aliases):
    # Longer phrases win at the same position; flexible spaces also accept line breaks.
    alternatives = [r"\s+".join(re.escape(part) for part in alias.split())
                    for alias in sorted(aliases, key=len, reverse=True)]
    return re.compile(r"\b(" + "|".join(alternatives) + r")\b", re.IGNORECASE)


WORD_PATTERN = alias_pattern(ALIAS_COMMANDS)
DRAW_PATTERN = alias_pattern(DRAW_ALIASES)
VERDICT_PATTERN = alias_pattern(WORD_ALIASES["вердикт"])


def match_word_command(text):
    drawing = DRAW_PATTERN.search(text)
    if drawing:
        return "нарисуй", text[drawing.end():].lstrip(" \t\r\n,:—-")
    if VERDICT_PATTERN.search(text):
        return "вердикт", ""
    match = WORD_PATTERN.search(text)
    return (ALIAS_COMMANDS[" ".join(match.group().lower().split())], "") if match else None


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
