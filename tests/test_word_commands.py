"""Group shortcuts, reply targets and sender identities without external services."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import Update
from telegram.ext import ApplicationHandlerStop

from commands.ai import AIRuntime, group_message
from commands.word_commands import WORD_COMMANDS, WORD_ALIASES, match_word_command


def message(text, *, message_id=10, chat_id=-1001, age=0, sender_chat=None, is_bot=False, reply=None):
    raw = {"message_id": message_id, "date": int(time.time() - age), "text": text,
           "chat": {"id": chat_id, "type": "supergroup", "title": "test"},
           "from": {"id": 101, "is_bot": is_bot, "first_name": "Тест", "username": "tester"}}
    if sender_chat:
        raw["sender_chat"] = sender_chat
    if reply:
        raw["reply_to_message"] = reply
    return Update.de_json({"update_id": message_id, "message": raw}, None)


class WordCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from commands.pole import pole_games
        from commands.entertainment import last_cat_time
        pole_games.clear()
        last_cat_time.clear()
        self.addCleanup(pole_games.clear)
        self.addCleanup(last_cat_time.clear)
        self.env = patch.dict("os.environ", {"ALLOWED_GROUP_ID": "-1001", "GROQ_API_KEY": "",
                                             "AI_REPLY_PROBABILITY": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = AIRuntime(started_at=time.time() - 20)
        self.state.client.text = AsyncMock(return_value="AI")
        self.state.client.image = AsyncMock(return_value=b"\xff\xd8\xffimage")
        self.context = SimpleNamespace(bot_data={"ai_runtime": self.state}, bot=SimpleNamespace(id=9001),
                                       args=["original args"])
        text_patch = patch("telegram.Message.reply_text", new_callable=AsyncMock)
        photo_patch = patch("telegram.Message.reply_photo", new_callable=AsyncMock)
        self.text = text_patch.start()
        self.photo = photo_patch.start()
        self.addCleanup(text_patch.stop)
        self.addCleanup(photo_patch.stop)

    async def trigger(self, update):
        with self.assertRaises(ApplicationHandlerStop):
            await group_message(update, self.context)

    def test_whole_words_case_and_drawing_priority(self):
        for text in ["котлета", "котировка", "мемный", "мемуары", "судьбоносный", "песочница", "пруфовый", "лохотрон"]:
            self.assertIsNone(match_word_command(text))
        self.assertEqual(match_word_command("Пришли МЕМ!"), ("мем", ""))
        self.assertEqual(match_word_command("Песня, а потом котик"), ("песня", ""))
        self.assertEqual(match_word_command("Котик? Бот, НАРИСУЙ: Рыжий кот, мем на стене!"),
                         ("нарисуй", "Рыжий кот, мем на стене!"))
        self.assertEqual(match_word_command("Открой ЗАЛ \n СЛАВЫ!"), ("слава", ""))
        self.assertEqual(match_word_command("Кошка? СГЕНЕРИРУЙ \n КАРТИНКУ: Котёнок и мем."),
                         ("нарисуй", "Котёнок и мем."))

    async def test_synonyms_dispatch_to_same_commands_instead_of_ai(self):
        examples = {
            "котик": ["Кот!", "кошка", "киська", "КИСЬКУ", "котёнок", "котенок", "котики", "мяу"],
            "судьба": ["погадай", "предскажи"],
            "песня": ["песню", "музычка", "трек"],
            "мем": ["мемас", "прикол"],
            "казино": ["казик", "слоты"],
            "бурмалда": ["бурмалду", "бурмалдочка"],
            "слава": ["легенды", "зал славы"],
            "пруф": ["пруфы", "подтверди"],
            "лох": ["лошара", "прожарь"],
        }
        handlers = {word: AsyncMock() for word in examples}
        index = 0
        with patch.dict(WORD_COMMANDS, handlers):
            for word, texts in examples.items():
                for text in texts:
                    update = message(text, message_id=100 + index)
                    await self.trigger(update)
                    await self.trigger(update)
                    index += 1
                self.assertEqual(handlers[word].await_count, len(texts))
        self.state.client.text.assert_not_called()

    async def test_all_shortcuts_dispatch_once_without_groq_or_random_selection(self):
        handlers = {word: AsyncMock() for word in WORD_COMMANDS}
        with patch.dict(WORD_COMMANDS, handlers):
            for index, (word, handler) in enumerate(handlers.items()):
                update = message("Бот, " + WORD_ALIASES[word][0].upper() + "!", message_id=20 + index)
                await self.trigger(update)
                await self.trigger(update)
                handler.assert_awaited_once()
                command_update, context = handler.call_args.args
                self.assertEqual(command_update.message.message_id, update.message.message_id)
                self.assertEqual(context.args, [])
        self.assertEqual(self.context.args, ["original args"])
        self.state.client.text.assert_not_called()

    async def test_old_unapproved_bot_edited_and_slash_messages_do_not_trigger(self):
        edited = Update.de_json({"update_id": 99, "edited_message": {
            "message_id": 1, "date": int(time.time()), "text": "котик",
            "chat": {"id": -1001, "type": "supergroup", "title": "test"}}}, None)
        handler = AsyncMock()
        with patch.dict(WORD_COMMANDS, {"котик": handler}):
            for update in [message("котик", age=21), message("котик", chat_id=-999),
                           message("котик", is_bot=True), message("/cat котик"), edited]:
                await group_message(update, self.context)
        handler.assert_not_called()

    async def test_drawing_uses_description_and_replies_without_text_ai(self):
        update = message("Бот, сгенерируй картинку: Маленький КОТИК с гитарой, мем на стене.")
        await self.trigger(update)
        await self.trigger(update)
        self.state.client.image.assert_awaited_once_with("Маленький КОТИК с гитарой, мем на стене.")
        self.state.client.text.assert_not_called()
        self.photo.assert_awaited_once()
        self.assertEqual(self.photo.call_args.kwargs["reply_to_message_id"], 10)
        self.assertEqual(self.context.args, ["original args"])
        # Drawing retains its own cooldown.
        await self.trigger(message("нарисуй ещё кота", message_id=11))
        self.assertEqual(self.state.client.image.await_count, 1)
        self.text.assert_awaited_once()

    async def test_empty_drawing_prompts_for_description_without_generating(self):
        await self.trigger(message("Нарисуй"))
        self.state.client.image.assert_not_called()
        self.text.assert_awaited_once()
        self.assertEqual(self.text.call_args.kwargs["reply_to_message_id"], 10)

    async def test_cat_and_prediction_preserve_command_cooldowns_and_reply_targets(self):
        from commands.entertainment import last_cat_time
        last_cat_time.clear()
        with patch("commands.entertainment.fetch_cat_image", return_value=(200, "image/jpeg", b"cat")) as fetch:
            await self.trigger(message("котик"))
            self.photo.assert_awaited_once_with(b"cat", reply_to_message_id=10)
            await self.trigger(message("котик", message_id=11))
            fetch.assert_called_once()
            self.assertEqual(self.text.call_args.kwargs["reply_to_message_id"], 11)
        self.photo.reset_mock()
        await self.trigger(message("Судьба", message_id=12))
        self.assertEqual(self.photo.call_args.kwargs["reply_to_message_id"], 12)

    async def test_chat_senders_have_distinct_cooldowns_and_hall_replies(self):
        from commands.entertainment import last_cat_time
        last_cat_time.clear()
        with patch("commands.entertainment.fetch_cat_image", return_value=(200, "image/jpeg", b"cat")) as fetch:
            for index, sender in enumerate([{"id": -1001, "type": "supergroup", "title": "Анонимный админ"},
                                            {"id": -1002, "type": "channel", "title": "Поющий ведьмак"}]):
                await self.trigger(message("котик", message_id=30 + index, sender_chat=sender, is_bot=True))
            self.assertEqual(fetch.call_count, 2)
            self.assertIn(-1001, last_cat_time)
            self.assertIn(-1002, last_cat_time)
        self.photo.reset_mock()
        with patch("commands.hall.load_hall_data", return_value=[]), patch("commands.hall.build_binary_stream", return_value=None):
            await self.trigger(message("Слава", message_id=32, sender_chat={"id": -1001, "type": "supergroup", "title": "Админ"}))
        self.assertEqual(self.text.call_args.kwargs["reply_to_message_id"], 32)

    async def test_proof_and_roast_preserve_quoted_target(self):
        original = {"message_id": 5, "date": int(time.time() - 100), "text": "Моё сообщение",
                    "chat": {"id": -1001, "type": "supergroup", "title": "test"},
                    "from": {"id": 202, "is_bot": False, "first_name": "Лютик"}}
        for index, word in enumerate(["пруф", "лох"]):
            self.photo.reset_mock()
            await self.trigger(message(word, message_id=40 + index, reply=original))
            self.assertEqual(self.photo.call_args.kwargs["reply_to_message_id"], 5)
        self.assertIn("Лютик", self.photo.call_args.kwargs["caption"])

    async def test_shortcuts_stop_game_and_ai_processing(self):
        from commands.pole import pole_games
        pole_games[101] = {"chat_id": -1001}
        handler = AsyncMock()
        with patch.dict("os.environ", {"GROQ_API_KEY": "offline", "AI_REPLY_PROBABILITY": "1.0"}), \
                patch.dict(WORD_COMMANDS, {"мем": handler}):
            await self.trigger(message("Бот, пришли мем"))
        handler.assert_awaited_once()
        self.state.client.text.assert_not_called()
        self.assertIn(101, pole_games)
