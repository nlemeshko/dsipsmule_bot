"""AI provider contracts and Telegram routing, without real credentials or API calls."""

import base64
import json
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from commands.ai import AIRuntime, answer, draw_command, group_message, private_audio, transcribe_command
from services.ai import AIClient, AIError


def update(chat_id=-1001, chat_type="supergroup", age=0, message_id=10, text="Привет", **extra):
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    user = SimpleNamespace(id=101, is_bot=False)
    msg = SimpleNamespace(
        chat=chat, chat_id=chat_id, message_id=message_id, text=text, voice=None, audio=None,
        date=datetime.fromtimestamp(time.time() - age, timezone.utc), sender_chat=None,
        reply_to_message=None, reply_text=AsyncMock(), reply_photo=AsyncMock(),
    )
    for key, value in extra.items():
        setattr(msg, key, value)
    return SimpleNamespace(message=msg, effective_message=msg, effective_chat=chat, effective_user=user)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from commands.callback_handler import user_states
        from commands.pole import pole_games
        user_states.clear()
        pole_games.clear()
        self.env = patch.dict("os.environ", {"GROQ_API_KEY": "offline", "ALLOWED_GROUP_ID": "-1001, -1002",
                                             "AI_REPLY_PROBABILITY": "1.0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = AIRuntime(started_at=time.time() - 20)
        self.state.client.text = AsyncMock(return_value="Ответ Ведьмака")
        self.state.client.transcribe = AsyncMock(return_value="Привет из голосового")
        self.state.client.image = AsyncMock(return_value=b"\xff\xd8\xffimage")
        self.context = SimpleNamespace(bot_data={"ai_runtime": self.state},
                                       bot=SimpleNamespace(id=9001, get_file=AsyncMock()), args=[])

    async def test_real_telegram_updates_from_all_group_sender_types(self):
        from telegram import Update
        users = [{"id": 101, "is_bot": False, "first_name": "Обычный участник"},
                 {"id": 202, "is_bot": False, "first_name": "Другой участник"},
                 {"id": 1087968824, "is_bot": True, "first_name": "Group"},
                 {"id": 136817688, "is_bot": True, "first_name": "Channel"}]
        senders = [None, None, {"id": -1001, "type": "supergroup", "title": "test"},
                   {"id": -1002699357832, "type": "channel", "title": "Поющий ведьмак"}]
        with patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "1.0"}), patch("telegram.Message.reply_text", new_callable=AsyncMock) as reply:
            for index, (user, sender) in enumerate(zip(users, senders)):
                message = {"message_id": 80 + index, "date": int(time.time()),
                           "chat": {"id": -1001, "type": "supergroup", "title": "test"},
                           "from": user, "text": "Как дела?"}
                if sender:
                    message["sender_chat"] = sender
                msg = Update.de_json({"update_id": index, "message": message}, None)
                await group_message(msg, self.context)
                await group_message(msg, self.context)
        self.assertEqual(self.state.client.text.await_count, len(users))
        self.assertEqual(reply.await_count, len(users))

    async def test_only_new_unedited_allowed_human_messages_reach_api(self):
        messages = [update(age=21), update(age=301), update(age=-30), update(chat_id=-999),
                    update(chat_type="channel"), update(text="/start"), update(text=None)]
        edited = update()
        edited.message = None
        messages.append(edited)
        bot_message = update()
        bot_message.effective_user.is_bot = True
        messages.append(bot_message)
        messages.append(update(sender_chat=SimpleNamespace(id=-999)))
        messages.append(update(sender_chat=SimpleNamespace(id=-1001), is_automatic_forward=True))
        with patch("commands.ai.random.random", return_value=0):
            for msg in messages:
                await group_message(msg, self.context)
        self.state.client.text.assert_not_called()
        fresh = update()
        with patch("commands.ai.random.random", return_value=0):
            await group_message(fresh, self.context)
        self.state.client.text.assert_awaited_once_with("Привет")
        fresh.effective_message.reply_text.assert_awaited_once_with("Ответ Ведьмака")

    async def test_ten_percent_threshold_and_duplicate_updates(self):
        self.env10 = patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0.1"})
        self.env10.start()
        self.addCleanup(self.env10.stop)
        msg = update()
        with patch("commands.ai.random.random", return_value=0.10):
            await group_message(msg, self.context)
        with patch("commands.ai.random.random", return_value=0.01):
            # Replayed updates are not another chance to draw a random answer.
            await group_message(msg, self.context)
        self.state.client.text.assert_not_called()
        with patch("commands.ai.random.random", return_value=0.099):
            await group_message(update(message_id=11), self.context)
            await group_message(update(message_id=11), self.context)
        self.state.client.text.assert_awaited_once()

    async def test_group_cooldown_and_active_game(self):
        env10 = patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0.1"})
        env10.start()
        self.addCleanup(env10.stop)
        from commands.pole import pole_games
        pole_games[101] = {"chat_id": -1001}
        with patch("commands.ai.random.random", return_value=0):
            await group_message(update(), self.context)
            self.state.client.text.assert_not_called()
            pole_games.clear()
            await group_message(update(message_id=11), self.context)
            await group_message(update(message_id=12), self.context)
        self.state.client.text.assert_awaited_once()

    async def test_full_probability_answers_consecutive_messages_once(self):
        messages = [update(message_id=20, text="Первый пост"),
                    update(message_id=21, text="Следующий пост"),
                    update(message_id=22, text="Другой участник")]
        messages[2].effective_user.id = 202
        # The new default is 100% even without an explicit Secret setting.
        with patch.dict("os.environ"):
            import os
            os.environ.pop("AI_REPLY_PROBABILITY", None)
            with patch("commands.ai.random.random", return_value=0.999):
                for msg in messages:
                    await group_message(msg, self.context)
                    await group_message(msg, self.context)
                    msg.effective_message.reply_text.assert_awaited_once_with("Ответ Ведьмака")
        self.assertEqual(self.state.client.text.await_count, 3)

    async def test_zero_probability_disables_text_but_keeps_voice(self):
        file = SimpleNamespace(file_path="voice.oga", download_as_bytearray=AsyncMock(return_value=b"ogg"))
        self.context.bot.get_file.return_value = file
        voice = update(message_id=21, text=None, voice=SimpleNamespace(file_id="file", file_size=3, duration=2))
        with patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0"}), patch("commands.ai.random.random", return_value=0):
            await group_message(update(), self.context)
            await group_message(voice, self.context)
        self.state.client.text.assert_not_called()
        self.state.client.transcribe.assert_awaited_once_with(b"ogg", "voice.ogg")

    async def test_bot_prefix_bypasses_probability_cooldowns_and_active_game(self):
        from commands.pole import pole_games
        pole_games[101] = {"chat_id": -1001}
        self.state.throttle("text", -1001, 15, group=True)
        self.state.throttle("text", 101, 5)
        with patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0"}), patch("commands.ai.random.random", return_value=0.99):
            for index, text in enumerate(["Бот, объясни", "бот помоги", "  БОТ!", "Бот"]):
                msg = update(message_id=30 + index, text=text)
                await group_message(msg, self.context)
                await group_message(msg, self.context)
                msg.effective_message.reply_text.assert_awaited_once_with("Ответ Ведьмака")
            pole_games.clear()
            for index, text in enumerate(["Ботинок", "Ботаника", "Привет, Бот"]):
                await group_message(update(message_id=40 + index, text=text), self.context)
        self.assertEqual(self.state.client.text.await_count, 4)

    async def test_reply_to_this_bot_includes_quote_and_answers_once_at_zero_probability(self):
        original = SimpleNamespace(from_user=SimpleNamespace(id=9001, is_bot=True),
                                   text="Старый ответ бота", caption=None)
        with patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0"}):
            for index, quote in enumerate([None, SimpleNamespace(text="Выбранная цитата")]):
                msg = update(message_id=50 + index, text="Почему?", reply_to_message=original, quote=quote)
                await group_message(msg, self.context)
                await group_message(msg, self.context)
                expected = quote.text if quote else original.text
                self.state.client.text.assert_awaited_with(
                    "Твоё предыдущее сообщение (цитата):\n" + expected
                    + "\n\nНовое сообщение участника:\nПочему?")
                msg.effective_message.reply_text.assert_awaited_once()
        self.assertEqual(self.state.client.text.await_count, 2)

    async def test_replies_to_other_authors_and_plain_quotes_are_not_direct_requests(self):
        with patch.dict("os.environ", {"AI_REPLY_PROBABILITY": "0"}):
            for index, author in enumerate([SimpleNamespace(id=202, is_bot=False),
                                            SimpleNamespace(id=9002, is_bot=True), None]):
                original = SimpleNamespace(from_user=author, text="Бот, привет")
                await group_message(update(message_id=60 + index, text="Почему?", reply_to_message=original), self.context)
            await group_message(update(message_id=63, text="«Ответ бота»", quote=SimpleNamespace(text="Ответ бота")), self.context)
        self.state.client.text.assert_not_called()

    async def test_direct_requests_preserve_new_message_group_and_sender_checks(self):
        original = SimpleNamespace(from_user=SimpleNamespace(id=9001, is_bot=True), text="Ответ")
        messages = [update(age=21), update(age=301), update(chat_id=-999), update(chat_type="channel"),
                    update(text="/start")]
        edited = update()
        edited.message = None
        bot_message = update()
        bot_message.effective_user.is_bot = True
        messages.extend([edited, bot_message])
        for msg in messages:
            msg.effective_message.reply_to_message = original
            if msg.effective_message.text != "/start":
                msg.effective_message.text = "Бот, привет"
            await group_message(msg, self.context)
        self.state.client.text.assert_not_called()

    async def test_new_group_voice_is_transcribed_without_random_selection(self):
        file = SimpleNamespace(file_path="voice.oga", download_as_bytearray=AsyncMock(return_value=b"ogg"))
        self.context.bot.get_file.return_value = file
        msg = update(text=None, voice=SimpleNamespace(file_id="file", file_size=3, duration=2))
        with patch("commands.ai.random.random", return_value=0.99):
            await group_message(msg, self.context)
            await group_message(msg, self.context)
        self.state.client.transcribe.assert_awaited_once_with(b"ogg", "voice.ogg")
        msg.effective_message.reply_text.assert_awaited_once_with("Расшифровка:\nПривет из голосового")

    async def test_old_voice_and_unapproved_group_are_never_downloaded(self):
        voice = SimpleNamespace(file_id="file", file_size=3, duration=2)
        for msg in [update(age=21, text=None, voice=voice), update(chat_id=-999, text=None, voice=voice)]:
            await group_message(msg, self.context)
        self.context.bot.get_file.assert_not_called()

    async def test_anonymous_admin_voice_is_transcribed_once(self):
        group_id = -1004445297166
        file = SimpleNamespace(file_path="voice.oga", download_as_bytearray=AsyncMock(return_value=b"ogg"))
        self.context.bot.get_file.return_value = file
        voice = SimpleNamespace(file_id="file", file_size=3, duration=2)
        msg = update(chat_id=group_id, text=None, voice=voice, sender_chat=SimpleNamespace(id=group_id))
        msg.effective_user = SimpleNamespace(id=1087968824, is_bot=True)
        with patch.dict("os.environ", {"ALLOWED_GROUP_ID": str(group_id)}):
            await group_message(msg, self.context)
            await group_message(msg, self.context)
        self.state.client.transcribe.assert_awaited_once_with(b"ogg", "voice.ogg")
        msg.effective_message.reply_text.assert_awaited_once_with("Расшифровка:\nПривет из голосового")

    async def test_anonymous_admin_text_keeps_new_only_group_and_probability_checks(self):
        anonymous = SimpleNamespace(id=-1001)
        with patch("commands.ai.random.random", return_value=0):
            for msg in [update(age=21, sender_chat=anonymous),
                        update(chat_id=-999, sender_chat=SimpleNamespace(id=-999)),
                        update(sender_chat=anonymous, is_automatic_forward=True)]:
                msg.effective_user = None
                await group_message(msg, self.context)
            self.state.client.text.assert_not_called()
            fresh = update(sender_chat=anonymous)
            fresh.effective_user = None
            await group_message(fresh, self.context)
        self.state.client.text.assert_awaited_once_with("Привет")

    async def test_channel_voice_in_allowed_group_is_transcribed_once(self):
        group_id, channel_id = -1004445297166, -1002699357832
        self.context.bot.get_file.return_value = SimpleNamespace(
            file_path="voice.oga", download_as_bytearray=AsyncMock(return_value=b"ogg"))
        voice = SimpleNamespace(file_id="file", file_size=3, duration=2)
        with patch.dict("os.environ", {"ALLOWED_GROUP_ID": str(group_id)}):
            for index, forwarded in enumerate([False, True]):
                self.state.users.clear()
                msg = update(chat_id=group_id, message_id=20 + index, text=None, voice=voice,
                             sender_chat=SimpleNamespace(id=channel_id, type="channel"),
                             is_automatic_forward=forwarded)
                msg.effective_user = None
                await group_message(msg, self.context)
                await group_message(msg, self.context)
                msg.effective_message.reply_text.assert_awaited_once_with("Расшифровка:\nПривет из голосового")
        self.assertEqual(self.state.client.transcribe.await_count, 2)
        self.state.client.text.assert_not_called()

    async def test_channel_text_and_direct_requests_in_allowed_group(self):
        group_id, channel_id = -1004445297166, -1002699357832
        sender = SimpleNamespace(id=channel_id, type="channel")
        original = SimpleNamespace(from_user=SimpleNamespace(id=9001, is_bot=True), text="Ответ бота")
        with patch.dict("os.environ", {"ALLOWED_GROUP_ID": str(group_id), "AI_REPLY_PROBABILITY": "0.1"}):
            # Ordinary text is still randomly selected for a channel identity.
            with patch("commands.ai.random.random", return_value=0):
                msg = update(chat_id=group_id, sender_chat=sender)
                msg.effective_user = SimpleNamespace(id=136817688, is_bot=True)
                await group_message(msg, self.context)
                msg.effective_message.reply_text.assert_awaited_once()
            # Addressing and quoting work even when selection/cooldowns would skip.
            with patch("commands.ai.random.random", return_value=0.99):
                for index, (text, reply) in enumerate([("Бот как твои дела?", None), ("Почему?", original)]):
                    msg = update(chat_id=group_id, message_id=20 + index, text=text,
                                 sender_chat=sender, reply_to_message=reply)
                    msg.effective_user = None
                    await group_message(msg, self.context)
                    await group_message(msg, self.context)
                    msg.effective_message.reply_text.assert_awaited_once()
        self.assertEqual(self.state.client.text.await_count, 3)

    async def test_every_group_voice_is_transcribed_regardless_of_sender_or_active_game(self):
        from commands.pole import pole_games
        pole_games[101] = {"chat_id": -1001}
        self.context.bot.get_file.return_value = SimpleNamespace(
            file_path="voice.oga", download_as_bytearray=AsyncMock(return_value=b"ogg"))
        voice = SimpleNamespace(file_id="file", file_size=3, duration=2)
        senders = [
            (SimpleNamespace(id=101, is_bot=False), None),
            (SimpleNamespace(id=101, is_bot=False), None),  # back-to-back voice notes
            (SimpleNamespace(id=202, is_bot=False), None),
            (SimpleNamespace(id=1087968824, is_bot=True), SimpleNamespace(id=-1001)),
            (None, SimpleNamespace(id=-1002699357832, type="channel")),
            (None, SimpleNamespace(id=-100999, type="supergroup")),
            (SimpleNamespace(id=303, is_bot=True), None),
            (None, None),
        ]
        with patch("commands.ai.random.random", return_value=0.99):
            for index, (user, sender_chat) in enumerate(senders):
                msg = update(message_id=100 + index, text=None, voice=voice,
                             sender_chat=sender_chat, is_automatic_forward=True)
                msg.effective_user = user
                await group_message(msg, self.context)
                await group_message(msg, self.context)
                msg.effective_message.reply_text.assert_awaited_once_with("Расшифровка:\nПривет из голосового")
        self.assertEqual(self.state.client.transcribe.await_count, len(senders))
        self.state.client.text.assert_not_called()

    async def test_channel_voice_keeps_age_edits_and_destination_group_checks(self):
        voice = SimpleNamespace(file_id="file", file_size=3, duration=2)
        sender = SimpleNamespace(id=-1002699357832, type="channel")
        edited = update(text=None, voice=voice, sender_chat=sender)
        edited.message = None
        messages = [update(text=None, voice=voice, sender_chat=sender, age=21),
                    update(text=None, voice=voice, sender_chat=sender, chat_id=-999),
                    update(text=None, voice=voice, sender_chat=sender, chat_type="channel"),
                    update(sender_chat=sender, is_automatic_forward=True), edited]
        with patch("commands.ai.random.random", return_value=0):
            for msg in messages:
                await group_message(msg, self.context)
        self.context.bot.get_file.assert_not_called()
        self.state.client.transcribe.assert_not_called()
        self.state.client.text.assert_not_called()

    async def test_anonymous_audio_keeps_moderation_routing(self):
        from commands.callback_handler import user_states, ANON_STATE
        user_states[101] = ANON_STATE
        msg = update(chat_id=101, chat_type="private", text=None, voice=SimpleNamespace(file_id="file"))
        with patch("commands.fsm_handler.handle_anon_voice", new=AsyncMock()) as moderation:
            await private_audio(msg, self.context)
        moderation.assert_awaited_once_with(msg, self.context)
        self.context.bot.get_file.assert_not_called()
        self.state.client.transcribe.assert_not_called()

    async def test_other_forms_do_not_consume_audio_as_ai(self):
        from commands.callback_handler import user_states, SONG_STATE
        user_states[101] = SONG_STATE
        await private_audio(update(chat_id=101, chat_type="private", text=None), self.context)
        self.state.client.transcribe.assert_not_called()

    async def test_oversized_audio_never_downloaded(self):
        msg = update(chat_id=101, chat_type="private", text=None,
                     voice=SimpleNamespace(file_id="file", file_size=21 * 1024 * 1024, duration=2))
        await private_audio(msg, self.context)
        self.context.bot.get_file.assert_not_called()
        msg.effective_message.reply_text.assert_awaited_once()

    async def test_explicit_commands_ignore_downtime_updates(self):
        self.context.args = ["картинка"]
        for handler in [draw_command, transcribe_command]:
            await handler(update(age=21), self.context)
        await answer(update(age=21), self.context, "старый вопрос")
        self.state.client.text.assert_not_called()
        self.state.client.image.assert_not_called()
        self.context.bot.get_file.assert_not_called()

    async def test_group_limit_errors_are_quiet_and_explicit_errors_visible(self):
        self.state.client.text.side_effect = AIError("Лимит нейросети исчерпан.")
        msg = update()
        with patch("commands.ai.random.random", return_value=0):
            await group_message(msg, self.context)
        msg.effective_message.reply_text.assert_not_called()
        self.state.users.clear()
        await answer(msg, self.context, "вопрос")
        msg.effective_message.reply_text.assert_awaited_once_with("Лимит нейросети исчерпан.")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_qwen_uses_dialogue_mode_and_gpt_oss_override_still_works(self):
        client = AIClient()
        client.request = AsyncMock(return_value={"choices": [{"message": {"content": "Ответ по-русски"}}]})
        with patch.dict("os.environ", {"GROQ_API_KEY": "offline", "GROQ_TEXT_MODEL": ""}):
            self.assertEqual(await client.text("Бот, привет"), "Ответ по-русски")
        payload = client.request.call_args.kwargs["payload"]
        self.assertEqual(payload["model"], "qwen/qwen3.8-27b")
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["reasoning_format"], "hidden")
        self.assertNotIn("include_reasoning", payload)
        with patch.dict("os.environ", {"GROQ_API_KEY": "offline", "GROQ_TEXT_MODEL": "openai/gpt-oss-120b"}):
            await client.text("Вопрос")
        payload = client.request.call_args.kwargs["payload"]
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertFalse(payload["include_reasoning"])
        self.assertNotIn("reasoning_format", payload)

    async def test_groq_text_and_speech_request_formats(self):
        client = AIClient()
        client.request = AsyncMock(return_value={"choices": [{"message": {"content": "<think>тайна</think>Ответ"}}]})
        with patch.dict("os.environ", {"GROQ_API_KEY": "offline", "GROQ_TEXT_MODEL": "openai/gpt-oss-20b"}):
            self.assertEqual(await client.text("Вопрос"), "Ответ")
            request = client.request.call_args
            self.assertEqual(request.args[1], "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(request.kwargs["payload"]["messages"][-1]["content"], "Вопрос")
            self.assertEqual(request.kwargs["payload"]["model"], "openai/gpt-oss-20b")
            client.request.return_value = {"text": " Расшифровка "}
            self.assertEqual(await client.transcribe(b"ogg", "voice.ogg"), "Расшифровка")
            self.assertTrue(client.request.call_args.args[1].endswith("/audio/transcriptions"))
            fields = client.request.call_args.kwargs["form"]._fields
            self.assertEqual({entry[0]["name"]: entry[2] for entry in fields}["file"], b"ogg")

    async def test_cloudflare_base64_image_and_success_validation(self):
        image = b"\xff\xd8\xffJPEG"
        client = AIClient()
        client.request = AsyncMock(return_value={"success": True, "result": {"image": base64.b64encode(image).decode()}})
        with patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "offline", "GROQ_API_KEY": "", "CLOUDFLARE_IMAGE_MODEL": ""}):
            self.assertEqual(await client.image("Кот"), image)
            form = client.request.call_args.kwargs["form"]
            self.assertTrue(form.is_multipart)
            self.assertEqual({field[0]["name"]: field[2] for field in form._fields},
                             {"prompt": "Кот", "width": "1024", "height": "1024"})
            self.assertTrue(client.request.call_args.args[1].endswith("/@cf/black-forest-labs/flux-2-klein-4b"))
            for data in [{"success": False}, {"success": True, "result": {"image": "invalid"}},
                         {"success": True, "result": {"image": base64.b64encode(b"not an image").decode()}}]:
                client.request.return_value = data
                with self.assertRaises(AIError):
                    await client.image("Кот")

    async def test_russian_description_is_translated_with_a_dedicated_prompt_and_no_added_style(self):
        from services.ai import IMAGE_TRANSLATION_PROMPT
        client = AIClient()
        image = {"success": True, "result": {"image": base64.b64encode(b"\xff\xd8\xffJPEG").decode()}}
        client.request = AsyncMock(side_effect=[{"choices": [{"message": {"content": "A small kitten"}}]}, image])
        with patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "offline", "GROQ_API_KEY": "offline", "CLOUDFLARE_IMAGE_MODEL": ""}):
            await client.image("Маленький котенок")
        calls = client.request.call_args_list
        self.assertEqual(calls[0].kwargs["payload"]["messages"], [
            {"role": "system", "content": IMAGE_TRANSLATION_PROMPT},
            {"role": "user", "content": "Маленький котенок"},
        ])
        form = calls[1].kwargs["form"]
        self.assertEqual({field[0]["name"]: field[2] for field in form._fields}["prompt"], "A small kitten")

    async def test_image_model_overrides_and_translation_failure_keep_generation_working(self):
        client = AIClient()
        image = {"success": True, "result": {"image": base64.b64encode(b"\xff\xd8\xffJPEG").decode()}}
        client.request = AsyncMock(return_value=image)
        client.text = AsyncMock(side_effect=AIError("Лимит"))
        with patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "offline", "GROQ_API_KEY": "offline"}):
            with patch.dict("os.environ", {"CLOUDFLARE_IMAGE_MODEL": "@cf/black-forest-labs/flux-2-klein-9b"}):
                await client.image("Котёнок")
                self.assertTrue(client.request.call_args.args[1].endswith("/flux-2-klein-9b"))
                form = client.request.call_args.kwargs["form"]
                self.assertEqual({field[0]["name"]: field[2] for field in form._fields}["prompt"], "Котёнок")
            with patch.dict("os.environ", {"CLOUDFLARE_IMAGE_MODEL": "@cf/black-forest-labs/flux-1-schnell"}):
                await client.image("A kitten")
                self.assertEqual(client.request.call_args.kwargs["payload"], {"prompt": "A kitten", "steps": 4})
            previous_calls = client.request.await_count
            with patch.dict("os.environ", {"CLOUDFLARE_IMAGE_MODEL": "unsupported"}):
                with self.assertRaises(AIError):
                    await client.image("Котёнок")
            self.assertEqual(client.request.await_count, previous_calls)

    async def test_missing_key_and_input_limits_do_not_call_network(self):
        with patch("services.ai.aiohttp.ClientSession") as session:
            client = AIClient()
            with self.assertRaises(AIError):
                await client.request("groq", "https://example.com", "")
            with self.assertRaises(AIError):
                await client.transcribe(b"x" * (20 * 1024 * 1024 + 1))
            with self.assertRaises(AIError):
                await client.image("x" * 2049)
            session.assert_not_called()

    async def test_429_blocks_followup_calls_without_retry_or_leaking_upstream_body(self):
        response = MagicMock(status=429, headers={"Retry-After": "120"})
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.post.return_value = response
        with patch("services.ai.aiohttp.ClientSession", return_value=session) as constructor:
            client = AIClient()
            for _ in range(2):
                with self.assertRaisesRegex(AIError, "Лимит"):
                    await client.request("groq", "https://example.com", "never-print-this-key", payload={})
            self.assertEqual(constructor.call_count, 1)
            session.post.assert_called_once()
            response.json.assert_not_called()

    async def test_http_success_is_parsed_by_transport(self):
        async def chunks(_):
            yield json.dumps({"text": "test"}).encode()
        response = MagicMock(status=200)
        response.content.iter_chunked = chunks
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.post.return_value = response
        with patch("services.ai.aiohttp.ClientSession", return_value=session):
            self.assertEqual(await AIClient().request("groq", "https://example.com", "offline", payload={}), {"text": "test"})


if __name__ == "__main__":
    unittest.main()
