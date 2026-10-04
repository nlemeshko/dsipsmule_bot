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
        self.env = patch.dict("os.environ", {"GROQ_API_KEY": "offline", "ALLOWED_GROUP_ID": "-1001, -1002"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = AIRuntime(started_at=time.time() - 20)
        self.state.client.text = AsyncMock(return_value="Ответ Ведьмака")
        self.state.client.transcribe = AsyncMock(return_value="Привет из голосового")
        self.state.client.image = AsyncMock(return_value=b"\xff\xd8\xffimage")
        self.context = SimpleNamespace(bot_data={"ai_runtime": self.state}, bot=SimpleNamespace(get_file=AsyncMock()), args=[])

    async def test_only_new_unedited_allowed_human_messages_reach_api(self):
        messages = [update(age=21), update(age=301), update(age=-30), update(chat_id=-999),
                    update(chat_type="channel"), update(text="/start"), update(text=None)]
        edited = update()
        edited.message = None
        messages.append(edited)
        bot_message = update()
        bot_message.effective_user.is_bot = True
        messages.append(bot_message)
        messages.append(update(sender_chat=SimpleNamespace(id=-1001)))
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
        from commands.pole import pole_games
        pole_games[101] = {"chat_id": -1001}
        with patch("commands.ai.random.random", return_value=0):
            await group_message(update(), self.context)
            self.state.client.text.assert_not_called()
            pole_games.clear()
            await group_message(update(message_id=11), self.context)
            await group_message(update(message_id=12), self.context)
        self.state.client.text.assert_awaited_once()

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
        with patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "offline"}):
            self.assertEqual(await client.image("Кот"), image)
            self.assertEqual(client.request.call_args.kwargs["payload"], {"prompt": "Кот", "steps": 4})
            self.assertTrue(client.request.call_args.args[1].endswith("/@cf/black-forest-labs/flux-1-schnell"))
            for data in [{"success": False}, {"success": True, "result": {"image": "invalid"}},
                         {"success": True, "result": {"image": base64.b64encode(b"not an image").decode()}}]:
                client.request.return_value = data
                with self.assertRaises(AIError):
                    await client.image("Кот")

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
