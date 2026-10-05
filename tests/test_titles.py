"""Durable voting, Telegram routing and restart recovery without real API calls."""

import asyncio
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError
from telegram.error import BadRequest, NetworkError
from telegram.ext import ApplicationHandlerStop
from commands.ai import AIRuntime, group_message
from commands.titles import titles_callback, process_pending, split_table
from commands.word_commands import match_word_command
from services import titles
from storage import fun as storage
from test_ai import update
from test_hall_storage import FakeS3


class Setup:
    def setup_storage(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"DATA_DIR": directory.name, "ALLOWED_GROUP_ID": "-1001,-1002"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.client = FakeS3()
        backend = patch.object(storage, "remote_storage", return_value=(self.client, "bucket", "fun.json"))
        backend.start()
        self.addCleanup(backend.stop)


class StorageTests(Setup, unittest.TestCase):
    def setUp(self):
        self.setup_storage()

    def test_one_active_round_votes_replace_and_restart_keeps_results(self):
        poll = titles.start(-1001, 11, 101, "Никита")
        self.assertEqual(titles.start(-1001, 12, 101, "Другой ник"), poll)
        titles.vote(poll["token"], -1001, 202, "legend")
        titles.vote(poll["token"], -1001, 202, "bore")
        self.assertEqual(titles.counts(titles.vote(poll["token"], -1001, 202, "bore")), {"legend": 0, "bore": 1})
        storage.state_path().unlink()
        titles.attach(poll["token"], 100)
        with patch("services.titles.time.time", return_value=poll["until"] + 1):
            closed = titles.due(poll["token"])
            with self.assertRaises(ValueError):
                titles.vote(poll["token"], -1001, 303, "legend")
        self.assertEqual(closed["result"], "bore")
        self.assertEqual(titles.leaderboard()[0][0], "101")
        self.assertEqual(titles.leaderboard()[0][1]["name"], "Никита")
        self.assertIn(poll["token"], titles.pending())
        titles.mark_reported(poll["token"])
        self.assertEqual(titles.pending(), {})

    def test_tie_and_no_votes_do_not_replace_previous_title(self):
        poll = titles.start(-1001, 11, 101, "Никита")
        titles.vote(poll["token"], -1001, 202, "legend")
        with patch("services.titles.time.time", return_value=poll["until"] + 1):
            titles.due(poll["token"])
            second = titles.start(-1002, 12, 101, "Никита")
        previous = titles.leaderboard()
        titles.vote(second["token"], -1002, 202, "legend")
        titles.vote(second["token"], -1002, 303, "bore")
        with patch("services.titles.time.time", return_value=second["until"] + 1):
            self.assertEqual(titles.due(second["token"])["result"], "tie")
            third = titles.start(-1002, 13, 101, "Никита")
        with patch("services.titles.time.time", return_value=third["until"] + 1):
            self.assertEqual(titles.due(third["token"])["result"], "empty")
        self.assertEqual(titles.leaderboard(), previous)

    def test_other_chat_forged_choice_and_s3_failure_do_not_change_votes(self):
        poll = titles.start(-1001, 11, 101, "Никита")
        before = self.client.body
        for chat, choice in [(-1002, "legend"), (-1001, "forged")]:
            with self.assertRaises(ValueError):
                titles.vote(poll["token"], chat, 202, choice)
        self.client.fail_write = True
        with self.assertRaises(ClientError):
            titles.vote(poll["token"], -1001, 202, "legend")
        self.assertEqual(self.client.body, before)
        self.client.fail_read = True
        with self.assertRaises(ClientError):
            titles.leaderboard()

    def test_concurrent_voters_do_not_lose_votes(self):
        poll = titles.start(-1001, 11, 101, "Никита")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda uid: titles.vote(poll["token"], -1001, uid, "legend"), range(30)))
        self.assertEqual(titles.counts(titles.due(poll["token"]))["legend"], 30)

    def test_corrupt_poll_is_rejected_without_overwriting_the_object(self):
        poll = titles.start(-1001, 11, 101, "Никита")
        before = self.client.body
        with self.assertRaises(ValueError):
            storage.update_state(lambda state: (True, state["community"]["title_polls"][poll["token"]].update(votes={"202": "forged"})))
        self.assertEqual(self.client.body, before)

    def test_all_participants_fit_paginated_table_without_dropping_rows(self):
        rows = [(str(uid), {"name": f"Участник {uid}" + "a" * 70, "choice": "legend" if uid % 2 else "bore",
                           "counts": {"legend": 2, "bore": 1}}) for uid in range(100)]
        pages = split_table(rows)
        self.assertTrue(all(len(page) <= 3500 for page in pages))
        self.assertEqual("".join(pages).count("• Участник"), 100)


class RoutingTests(Setup, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.setup_storage()
        self.bot = SimpleNamespace(id=9001, send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
                                   edit_message_text=AsyncMock())
        state = AIRuntime(time.time() - 20)
        state.client.text = AsyncMock()
        self.context = SimpleNamespace(bot=self.bot, bot_data={"ai_runtime": state}, user_data={}, args=[])

    async def trigger(self, word, **kwargs):
        msg = update(text=word, **kwargs)
        with self.assertRaises(ApplicationHandlerStop):
            await group_message(msg, self.context)
        return msg

    async def test_word_starts_poll_for_author_once_and_other_triggers_reuse_it(self):
        self.assertEqual(match_word_command("котик, ну ты НЕГР!"), ("вердикт", ""))
        self.assertEqual(match_word_command("Нарисуй гея"), ("нарисуй", "гея"))
        msg = await self.trigger("ГЕЙ!", reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=777)))
        await self.trigger("ГЕЙ!")
        await self.trigger("негр", message_id=11)
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(self.bot.send_message.call_args.kwargs["reply_to_message_id"], msg.message.message_id)
        self.assertIn("Гей или Негр?", self.bot.send_message.call_args.kwargs["text"])
        self.assertIn("Гей: 0 · Негр: 0", self.bot.send_message.call_args.kwargs["text"])
        buttons = self.bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0]
        self.assertEqual([button.text for button in buttons], ["Гей", "Негр"])
        poll = next(iter(storage.load_state()["community"]["title_polls"].values()))
        self.assertEqual([button.callback_data for button in buttons],
                         [f"titles:{poll['token']}:legend", f"titles:{poll['token']}:bore"])
        self.assertEqual(poll["target"], "101")
        self.context.bot_data["ai_runtime"].client.text.assert_not_called()
        self.assertEqual(poll["message_id"], 99)

    async def test_old_disallowed_and_bot_messages_never_create_votes(self):
        for msg in [update(text="негр", age=30), update(text="гей", chat_id=-999)]:
            await group_message(msg, self.context)
        msg = update(text="гей")
        msg.effective_user.is_bot = True
        await group_message(msg, self.context)
        self.bot.send_message.assert_not_called()
        self.assertEqual(storage.load_state()["community"], {})

    async def test_callback_vote_is_durable_and_rejects_other_group(self):
        await self.trigger("негр")
        token = next(iter(titles.pending()))
        query = SimpleNamespace(data=f"titles:{token}:legend", answer=AsyncMock())
        msg = update()
        callback = SimpleNamespace(callback_query=query, effective_chat=msg.effective_chat,
                                   effective_user=SimpleNamespace(id=202, is_bot=False))
        await titles_callback(callback, self.context)
        self.assertEqual(titles.counts(titles.due(token)), {"legend": 1, "bore": 0})
        self.bot.edit_message_text.side_effect = NetworkError("offline")
        await titles_callback(callback, self.context)
        self.assertEqual(query.answer.call_args.args[0], "Голос сохранён")
        callback.effective_chat = SimpleNamespace(id=-1002, type="supergroup")
        await titles_callback(callback, self.context)
        self.assertIn("недоступно", query.answer.call_args.args[0])

    async def test_restart_closes_round_and_retry_does_not_duplicate_the_result(self):
        await self.trigger("гей")
        token = next(iter(titles.pending()))
        poll = titles.vote(token, -1001, 202, "legend")
        storage.state_path().unlink()
        application = SimpleNamespace(bot=self.bot, bot_data={"title_pending": titles.pending()})
        self.bot.edit_message_text.side_effect = NetworkError("offline")
        with patch("services.titles.time.time", return_value=poll["until"] + 1):
            await process_pending(application)
            self.assertEqual(titles.leaderboard()[0][1]["choice"], "legend")
            self.assertIn(token, titles.pending())
            self.bot.edit_message_text.side_effect = BadRequest("Message is not modified")
            await process_pending(application)
            await process_pending(application)
        self.assertEqual(self.bot.edit_message_text.await_count, 2)
        self.assertEqual(titles.pending(), {})
        text = self.bot.edit_message_text.call_args.kwargs["text"]
        self.assertIn("Итог: Гей!", text)
        self.assertIn("Общие итоги «Гей / Негр»", text)
        self.assertIsNone(self.bot.edit_message_text.call_args.kwargs["reply_markup"])

    async def test_failed_publication_is_recovered_from_durable_pending_record(self):
        self.bot.send_message.side_effect = NetworkError("offline")
        msg = await self.trigger("гей")
        self.assertIn("Не удалось", msg.message.reply_text.call_args.args[0])
        token = next(iter(titles.pending()))
        self.bot.send_message.side_effect = None
        application = SimpleNamespace(bot=self.bot, bot_data={"title_pending": titles.pending()})
        await process_pending(application)
        self.assertEqual(titles.due(token)["message_id"], 99)
        self.assertGreater(application.bot_data["title_pending"][token], time.time())

    async def test_help_describes_current_vote_labels_and_shortcuts(self):
        from commands.help import help_command
        msg = update()
        await help_command(msg, self.context)
        text = msg.message.reply_text.call_args.args[0]
        self.assertIn('/verdict - голосование «Гей / Негр» за себя в группе на 5 минут', text)
        self.assertIn('гей, негр → /verdict', text)
        self.assertNotIn('легенда, душнила', text)
