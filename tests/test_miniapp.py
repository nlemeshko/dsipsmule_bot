"""Offline contract tests: signed identity, legacy workflows and moderation routing."""

import hashlib
import hmac
import json
import time
import unittest
import tempfile
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from telegram import Message

from miniapp.auth import validate_init_data, miniapp_url
from miniapp.server import MiniAppServer

TOKEN = "123456:offline-test-token"


def signed(user_id=101, **overrides):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id, "first_name": "Тест", "username": "tester"})}
    fields.update(overrides)
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, "\n".join(f"{k}={v}" for k, v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class AuthTests(unittest.TestCase):
    def test_identity_is_signed_and_time_bounded(self):
        self.assertEqual(validate_init_data(signed(), TOKEN)["id"], 101)
        for raw in ["", signed().replace("tester", "attacker"), signed(auth_date="1"), signed(auth_date=str(int(time.time()) + 300)), signed() + "&auth_date=123"]:
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                validate_init_data(raw, TOKEN)

    def test_public_url_requires_https(self):
        self.assertEqual(miniapp_url(" https://bot.mdsn.work "), "https://bot.mdsn.work")
        for value in ["http://bot.mdsn.work", "https://user:pass@bot.mdsn.work", "https://", "https://bot.mdsn.work/#test"]:
            with self.assertRaises(ValueError):
                miniapp_url(value)


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from commands.callback_handler import user_states
        from commands.pole import pole_games
        user_states.clear()
        pole_games.clear()
        self.bot = SimpleNamespace(
            send_message=AsyncMock(), send_photo=AsyncMock(), send_voice=AsyncMock(), send_audio=AsyncMock(),
            get_file=AsyncMock(), username="dsip_test",
        )
        self.application = SimpleNamespace(bot=self.bot, user_data=defaultdict(dict), bot_data={})
        self.server = MiniAppServer(self.application, TOKEN)
        self.client = TestClient(TestServer(self.server.app))
        self.addAsyncCleanup(self.client.close)
        await self.client.start_server()
        self.headers = {"X-Telegram-Init-Data": signed()}
        self.number = 0

    async def asyncTearDown(self):
        await self.client.close()

    async def action(self, **body):
        self.server.session(101).last_action = 0
        self.number += 1
        body.setdefault("request_id", f"request-{self.number:04}")
        r = await self.client.post("/api/action", json=body, headers=self.headers)
        self.assertEqual(r.status, 200, await r.text())
        return await r.json()

    async def test_static_and_auth_boundary(self):
        r = await self.client.get("/")
        self.assertEqual(r.status, 200)
        self.assertIn("Content-Security-Policy", r.headers)
        for path in ["/api/bootstrap", "/api/media/unknown"]:
            r = await self.client.get(path)
            self.assertEqual(r.status, 401)
        r = await self.client.post("/api/action", headers=self.headers, json={"action": "command", "command": "arbitrary", "request_id": "request-0000"})
        self.assertEqual(r.status, 400)
        self.bot.send_message.assert_not_called()

    async def test_anonymous_flow_reuses_moderation_and_is_idempotent(self):
        data = await self.action(action="callback", callback="button1")
        self.assertEqual(data["state"], "anon_waiting_text")
        media = data["messages"][0]["media"]
        with patch("commands.admin_notifications.get_admin_ids", return_value=[999, 101]):
            data = await self.action(action="message", text="Анонимный текст", request_id="anon-request")
            self.assertIsNone(data["state"])
            self.assertIn("модерацию", data["messages"][-1]["text"])
            self.assertEqual(self.bot.send_message.await_count, 2)
            await self.action(action="message", text="Анонимный текст", request_id="anon-request")
            self.assertEqual(self.bot.send_message.await_count, 2)
        r = await self.client.get(f"/api/media/{media}", headers=self.headers)
        self.assertEqual(r.status, 200)
        r = await self.client.get(f"/api/media/{media}", headers={"X-Telegram-Init-Data": signed(202)})
        self.assertEqual(r.status, 404)

    async def test_prediction_and_roast_reply_context(self):
        data = await self.action(action="command", command="prediction")
        self.assertTrue(data["messages"])
        data = await self.action(action="command", command="roast", target="Исполнитель")
        self.assertIn("Исполнитель", data["messages"][-1]["text"])

    async def test_pole_game_and_reset(self):
        data = await self.action(action="command", command="pole")
        self.assertTrue(data["playing"])
        from commands.pole import pole_games
        word = pole_games[101]["word"]
        data = await self.action(action="message", text=word)
        self.assertFalse(data["playing"])
        self.assertIn("Поздравляем", data["messages"][-1]["text"])
        self.assertNotIn("🤔 Думаю...", [m["text"] for m in data["messages"]])
        data = await self.action(action="reset")
        self.assertEqual(data["messages"], [])

    async def test_photo_upload_uses_server_owned_file_id(self):
        await self.action(action="callback", callback="button1")
        attachment = Message.de_json({"message_id": 10, "date": int(time.time()), "chat": {"id": 101, "type": "private"}, "photo": [{"file_id": "safe-file-id", "file_unique_id": "unique", "width": 20, "height": 20}]}, None)
        self.bot.send_photo.return_value = attachment
        form = FormData()
        for key, value in {"request_id": "upload-request", "kind": "photo", "text": "Подпись"}.items():
            form.add_field(key, value)
        form.add_field("file", b"fake-image", filename="image.jpg", content_type="image/jpeg")
        self.server.session(101).last_action = 0
        with patch("commands.admin_notifications.get_admin_ids", return_value=[999]):
            r = await self.client.post("/api/upload", data=form, headers=self.headers)
        self.assertEqual(r.status, 200, await r.text())
        data = await r.json()
        self.assertIsNone(data["state"])
        self.assertEqual(self.bot.send_photo.await_count, 2)
        self.assertEqual(self.bot.send_photo.call_args.kwargs["photo"], "safe-file-id")


    async def test_all_submission_buttons_and_personal_chat(self):
        for callback, state in [("button2", "song_waiting_text"), ("button3", "rate_waiting_link"), ("button6", "promote_waiting_link")]:
            with self.subTest(callback=callback), patch("commands.admin_notifications.get_admin_ids", return_value=[999]):
                data = await self.action(action="callback", callback=callback)
                self.assertEqual(data["state"], state)
                data = await self.action(action="message", text="https://www.smule.com/test")
                self.assertIsNone(data["state"])
        data = await self.action(action="message", text="Привет")
        self.assertIn("Привет, Тест", data["messages"][-1]["text"])

    async def test_hall_and_vote_persist_without_touching_repository(self):
        from commands.hall import load_hall_data
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATA_DIR": directory}):
            data = await self.action(action="command", command="hall", text="legend test-nominee")
            self.assertIn("Новая номинация", data["messages"][-1]["text"])
            data = await self.action(action="command", command="vote", text="legend test-nominee")
            nominee = next(r for r in load_hall_data() if r["name"] == "test-nominee")
            self.assertEqual(nominee["votes"], "2")
            data = await self.action(action="command", command="halllist")
            self.assertIn("test-nominee", data["messages"][-1]["text"])

    async def test_song_sources_and_media_commands_are_rendered(self):
        with patch("commands.callback_handler.fetch_song_of_the_day", return_value={"list": [{"title": "Песня", "artist": "Артист", "web_url": "/song", "cover_url": "https://example.com/cover.jpg"}]}):
            data = await self.action(action="callback", callback="button4")
        self.assertIn("https://www.smule.com/song", data["messages"][-1]["text"])
        with patch("commands.entertainment.get_random_russian_song", return_value=("Трек", "Артист", "https://example.com/song")):
            data = await self.action(action="command", command="random")
        self.assertIn("Трек", data["messages"][-1]["text"])
        with patch("commands.entertainment.fetch_cat_image", return_value=(200, "image/jpeg", b"image")):
            data = await self.action(action="command", command="cat")
        self.assertEqual(data["messages"][-1]["kind"], "photo")


    async def test_memes_casino_and_ai_voice(self):
        with patch("commands.entertainment.fetch_memes", return_value={"success": True, "data": {"memes": [{"url": "https://example.com/meme.jpg"}]}}):
            data = await self.action(action="command", command="meme")
        self.assertEqual(data["messages"][-1]["url"], "https://example.com/meme.jpg")
        with patch("commands.entertainment.asyncio.sleep", new=AsyncMock()):
            data = await self.action(action="command", command="casino")
        self.assertTrue(any("ПОЗДРАВЛЯЕМ" in m["text"] or "следующий раз" in m["text"] for m in data["messages"]))
        client = SimpleNamespace(
            chat=SimpleNamespace(create_chat=AsyncMock(return_value=(SimpleNamespace(chat_id="chat"), None)), send_message=AsyncMock(return_value=SimpleNamespace(turn_id="turn", primary_candidate_id="candidate", get_primary_candidate=lambda: SimpleNamespace(text="Ответ")))),
            utils=SimpleNamespace(generate_speech=AsyncMock(return_value=b"speech")), close_session=AsyncMock(),
        )
        with patch("commands.ask.CHARACTER_AI_AVAILABLE", True), patch("commands.ask.get_client", new=AsyncMock(return_value=client), create=True), patch.dict("os.environ", {"CHARACTER_AI_TOKEN": "test", "CHARACTER_ID": "test", "CHARACTER_VOICE_ID": "test"}):
            data = await self.action(action="command", command="ask", text="Как дела?")
        self.assertTrue(any(m["kind"] == "voice" for m in data["messages"]))
        self.assertNotIn("Думаю...", [m["text"] for m in data["messages"]])
        client.close_session.assert_awaited_once()



    async def test_anonymous_audio_and_voice_forwarding(self):
        for kind in ["audio", "voice"]:
            await self.action(action="callback", callback="button1")
            attachment = Message.de_json({"message_id": 10, "date": int(time.time()), "chat": {"id": 101, "type": "private"}, kind: {"file_id": f"{kind}-file", "file_unique_id": "unique", "duration": 1}}, None)
            method = getattr(self.bot, f"send_{kind}")
            method.return_value = attachment
            form = FormData()
            form.add_field("request_id", f"upload-{kind}")
            form.add_field("kind", kind)
            form.add_field("file", b"audio", filename="audio.ogg", content_type="audio/ogg")
            self.server.session(101).last_action = 0
            with patch("commands.admin_notifications.get_admin_ids", return_value=[999]):
                r = await self.client.post("/api/upload", data=form, headers=self.headers)
            self.assertEqual(r.status, 200, await r.text())
            self.assertIsNone((await r.json())["state"])
            self.assertEqual(method.await_count, 2)
            self.assertEqual(method.call_args.kwargs[kind], f"{kind}-file")

    async def test_bootstrap_restores_history_without_external_lookup(self):
        await self.action(action="callback", callback="button1")
        r = await self.client.get("/api/bootstrap", headers=self.headers)
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertEqual(data["state"], "anon_waiting_text")
        self.assertTrue(data["messages"])
        self.bot.get_file.assert_not_called()

    async def test_retired_actions_are_unavailable(self):
        for action in [{"action": "command", "command": "retired_event"}, {"action": "callback", "callback": "retired_button"}]:
            self.server.session(101).last_action = 0
            r = await self.client.post("/api/action", headers=self.headers, json={**action, "request_id": "retired-request"})
            self.assertEqual(r.status, 400)
        self.bot.send_message.assert_not_called()
        r = await self.client.get("/")
        html = await r.text()
        self.assertIn("Ведьмак", html)
        self.assertIn('href="https://dsipsmule.one"', html)
        self.assertNotIn("Конкурс", html)

    async def test_menu_launcher_and_chat_user_share_a_lock(self):
        from miniapp.locks import user_lock, locked_private
        from miniapp.bridge import AppBot, AppContext, make_update
        from commands.start import start_command
        session = self.server.session(101)
        self.assertIs(session.lock, user_lock(101))
        bot = AppBot(self.bot, {"id": 101, "first_name": "Тест"}, session, self.server.media)
        update = make_update(bot, "/start")
        capture = AsyncMock()
        with patch.dict("os.environ", {"MINI_APP_URL": "https://bot.mdsn.work"}), patch.object(AppBot, "send_message", capture):
            await locked_private(start_command)(update, AppContext(self.application, bot, 101))
        markup = capture.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].web_app.url, "https://bot.mdsn.work")
        self.assertEqual(markup.inline_keyboard[1][0].url, "https://dsipsmule.one")
        self.assertIn("Ведьмак", capture.call_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
