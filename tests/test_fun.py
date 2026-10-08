"""Persistent cards, global counters/votes and shared game callbacks."""

import asyncio
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop
from commands.ai import AIRuntime, answer, group_message
from commands.fun import ded_command, passport_command, order_command, guess_command, guess_reply, mood_command, fun_callback
from services import fun
from storage import fun as storage
from test_ai import update
from test_hall_storage import FakeS3


class DurableFunTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"DATA_DIR": directory.name}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.client = FakeS3()
        backend = patch.object(storage, "remote_storage", return_value=(self.client, "bucket", "dsipsmule-bot/fun/state.json"))
        backend.start()
        self.addCleanup(backend.stop)
        fun.invalidate_mood()
        self.addCleanup(fun.invalidate_mood)

    def test_passport_and_order_are_identical_after_redeploy_name_change_and_concurrent_calls(self):
        passport = fun.permanent_card(101, "Никита", "passport")
        order = fun.permanent_card(101, "Никита", "order")
        storage.state_path().unlink()
        with ThreadPoolExecutor(max_workers=6) as pool:
            cards = list(pool.map(lambda _: fun.permanent_card(101, "Другой ник", "passport"), range(12)))
        self.assertTrue(all(card == passport for card in cards))
        self.assertEqual(fun.permanent_card(101, "Другой ник", "order"), order)
        self.assertEqual(self.client.writes, 2)
        self.assertNotEqual(fun.permanent_card(202, "Другой", "passport")["number"], passport["number"])

    def test_failed_s3_read_or_write_never_acknowledges_a_new_card(self):
        card = fun.permanent_card(101, "Никита", "passport")
        before = self.client.body
        self.client.fail_write = True
        with self.assertRaises(ClientError):
            fun.permanent_card(202, "Другой", "passport")
        self.assertEqual(self.client.body, before)
        self.assertEqual(fun.permanent_card(101, "Другой ник", "passport"), card)
        self.client.fail_read = True
        with self.assertRaises(ClientError):
            fun.permanent_card(101, "Другой ник", "passport")

    def test_global_ded_meter_survives_loss_of_local_files_and_replayed_messages(self):
        for index in range(1, 10):
            fun.mention_ded(-1001, index)
        self.assertEqual(fun.mention_ded(-1002, 1), 10)
        storage.state_path().unlink()
        self.assertIsNone(fun.mention_ded(-1002, 1))
        self.assertEqual(fun.ded_status(), {"count": 10, "anger": 100})
        fun.mention_ded(-1002, 2)
        self.assertEqual(fun.ded_status(), {"count": 11, "anger": 10})

    def test_concurrent_ded_mentions_do_not_lose_updates(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda index: fun.mention_ded(-1001, index), range(40)))
        self.assertEqual(fun.ded_status()["count"], 40)

    def test_global_mood_counts_one_vote_per_user_and_expires_after_redeploy(self):
        with patch("services.fun.time.time", return_value=1000):
            mood = fun.open_mood()
            fun.vote_mood(101, mood["token"], "tired")
            fun.vote_mood(101, mood["token"], "tired")
            result = fun.vote_mood(101, mood["token"], "lyutik")
            self.assertEqual(result["counts"], {mode: int(mode == "lyutik") for mode in fun.MOODS})
            storage.state_path().unlink()
            self.assertEqual(fun.open_mood()["token"], mood["token"])
            self.assertIn("микрофона", fun.mood_instruction())
        with patch("services.fun.time.time", return_value=4601):
            self.assertEqual(fun.mood_instruction(), "")
            with self.assertRaises(ValueError):
                fun.vote_mood(101, mood["token"], "tired")
            self.assertNotEqual(fun.open_mood()["token"], mood["token"])

    def test_every_mood_survives_remote_reload_and_changes_the_ai_instruction(self):
        mood = fun.open_mood()
        for mode, (_, instruction) in fun.MOODS.items():
            with self.subTest(mode=mode):
                result = fun.vote_mood(101, mood["token"], mode)
                self.assertEqual(result["mode"], mode)
                self.assertEqual(sum(result["counts"].values()), 1)
                storage.state_path().unlink()
                fun.invalidate_mood()
                self.assertEqual(fun.open_mood()["votes"], {"101": mode})
                self.assertEqual(fun.mood_instruction(), instruction)
        with self.assertRaises(ValueError):
            fun.vote_mood(101, mood["token"], "unknown")

    def test_guess_does_not_repeat_the_previous_song_and_accepts_every_catalogue_answer(self):
        self.assertGreaterEqual(len(fun.RIDDLES), 60)
        answers = [fun.normalize_answer(answer) for _, answer, _ in fun.RIDDLES]
        self.assertEqual(len(answers), len(set(answers)))
        for riddle in fun.RIDDLES:
            with self.subTest(answer=riddle[1]):
                with patch("services.fun.random.choice", return_value=riddle):
                    game = fun.start_guess(-1001)
                self.assertEqual(game["emoji"], riddle[0])
                self.assertEqual(fun.guess_button(-1001, game["token"], "hint")["hint"], riddle[2])
                result = fun.solve_guess(-1001, game["answer"].upper().replace("Ё", "Е"), 101, "Тест")
                self.assertEqual(result["status"], "won")
                with patch("services.fun.random.choice", side_effect=lambda choices: choices[0]) as choice:
                    following = fun.start_guess(-1001)
                self.assertNotIn(riddle, choice.call_args.args[0])
                self.assertNotEqual(following["answer"], game["answer"])
                fun.guess_button(-1001, following["token"], "end")

    def test_guess_persists_and_has_one_winner_without_modifying_passport(self):
        passport = fun.permanent_card(101, "Никита", "passport")
        game = fun.start_guess(-1001)
        storage.state_path().unlink()
        self.assertEqual(fun.start_guess(-1001), game)
        self.assertEqual(fun.solve_guess(-1001, "не та песня", 202, "Лютик")["status"], "wrong")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda uid: fun.solve_guess(-1001, game["answer"].upper().replace("Ё", "Е"), uid, "Участник"), [101, 202]))
        self.assertEqual([result["status"] for result in results].count("won"), 1)
        self.assertEqual(fun.permanent_card(101, "Другой ник", "passport"), passport)
        with self.assertRaises(ValueError):
            fun.guess_button(-1001, game["token"], "hint")

    def test_corrupt_remote_state_is_not_overwritten_and_cache_failure_keeps_remote_card(self):
        self.client.body = b'{"version":1,"people":{},"community":{"ded":{"count":-1}},"games":{}}'
        with self.assertRaises(ValueError):
            storage.initialize_storage()
        self.assertEqual(self.client.writes, 0)
        self.client.body = None
        with patch.object(storage, "cache", side_effect=OSError("readonly")):
            card = fun.permanent_card(101, "Никита", "passport")
        self.assertEqual(fun.permanent_card(101, "Никита", "passport"), card)


class FunRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"DATA_DIR": directory.name, "ALLOWED_GROUP_ID": "-1001,-1002", "GROQ_API_KEY": "offline"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.client = FakeS3()
        backend = patch.object(storage, "remote_storage", return_value=(self.client, "bucket", "fun.json"))
        backend.start()
        self.addCleanup(backend.stop)
        self.state = AIRuntime(time.time() - 20)
        self.state.client.text = AsyncMock(return_value="AI")
        self.context = SimpleNamespace(bot_data={"ai_runtime": self.state, "fun_ready": True},
                                       user_data={}, args=[], bot=SimpleNamespace(id=9001))
        fun.invalidate_mood()
        self.addCleanup(fun.invalidate_mood)

    async def test_passport_word_and_order_alias_are_permanent_and_not_extra_ai_replies(self):
        for index, word in enumerate(["паспорт", "паспорт", "награда", "орден"]):
            msg = update(message_id=20 + index, text=word)
            with self.assertRaises(ApplicationHandlerStop):
                await group_message(msg, self.context)
            msg.message.reply_text.assert_awaited_once()
            self.assertIn("Паспорт сквада" if index < 2 else "Постоянный орден", msg.message.reply_text.call_args.args[0])
            if index in {0, 2}:
                first = msg.message.reply_text.call_args.args[0]
            else:
                self.assertEqual(msg.message.reply_text.call_args.args[0], first)
        self.state.client.text.assert_not_called()

    async def test_ded_counter_is_global_deduplicated_and_does_not_block_word_commands(self):
        for index in range(9):
            msg = update(message_id=40 + index, text="дед")
            await group_message(msg, self.context)
            await group_message(msg, self.context)
        msg = update(chat_id=-1002, message_id=60, text="дед паспорт")
        with self.assertRaises(ApplicationHandlerStop):
            await group_message(msg, self.context)
        self.assertEqual(msg.message.reply_text.await_count, 2)
        self.assertEqual(fun.ded_status()["count"], 10)
        report = update(chat_id=101, chat_type="private")
        await ded_command(report, self.context)
        self.assertIn("100%", report.message.reply_text.call_args.args[0])

    async def test_guess_answers_use_game_and_do_not_consume_normal_group_messages(self):
        msg = update(text="/guess")
        await guess_command(msg, self.context)
        game = fun.guess_game(-1001)
        normal = update(message_id=11, text="Привет всем")
        self.assertFalse(await guess_reply(normal, self.context, automatic=True))
        correct = update(message_id=12, text=game["answer"])
        with self.assertRaises(ApplicationHandlerStop):
            await group_message(correct, self.context)
        self.assertIn("угадано", correct.message.reply_text.call_args.args[0])
        self.assertNotIn(-1001, self.context.bot_data["fun_games_active"])

    async def test_group_quiz_does_not_change_the_same_users_private_game_mode(self):
        private = update(chat_id=101, chat_type="private", text="/guess")
        await guess_command(private, self.context)
        personal_game = fun.guess_game(101)
        group = update(text="/guess")
        await guess_command(group, self.context)
        game = fun.guess_game(-1001)
        self.assertTrue(self.context.user_data["fun_guess"])
        correct = update(message_id=12, text=game["answer"])
        self.assertTrue(await guess_reply(correct, self.context, automatic=True))
        self.assertTrue(self.context.user_data["fun_guess"])
        self.assertEqual(fun.guess_game(101), personal_game)

    async def test_private_pole_game_takes_over_from_guess_without_consuming_the_move(self):
        from commands.message_handler import handle_personal_message
        from commands.pole import pole_games
        self.context.user_data["fun_guess"] = True
        pole_games[101] = {"chat_id": 101}
        msg = update(chat_id=101, chat_type="private", text="Буква")
        msg.effective_user.first_name = "Никита"
        try:
            with patch("commands.pole.handle_pole_message", new=AsyncMock()) as pole:
                await handle_personal_message(msg, self.context)
            pole.assert_awaited_once_with(msg, self.context)
            self.assertNotIn("fun_guess", self.context.user_data)
        finally:
            pole_games.pop(101, None)

    async def test_mood_votes_update_the_poll_without_sending_new_messages(self):
        for chat_id, chat_type in [(-1001, "supergroup"), (101, "private")]:
            with self.subTest(chat_type=chat_type):
                command = update(chat_id=chat_id, chat_type=chat_type, text="/mood")
                await mood_command(command, self.context)
                command.message.reply_text.assert_awaited_once()
                markup = command.message.reply_text.call_args.kwargs["reply_markup"]
                message = SimpleNamespace(reply_text=AsyncMock(), edit_text=AsyncMock())
                callback = SimpleNamespace(
                    callback_query=SimpleNamespace(data="", answer=AsyncMock()),
                    effective_chat=command.effective_chat, effective_user=command.effective_user,
                    effective_message=message,
                )
                for index in [1, 2]:
                    callback.callback_query.data = markup.inline_keyboard[index][0].callback_data
                    callback.callback_query.answer.reset_mock()
                    await fun_callback(callback, self.context)
                    callback.callback_query.answer.assert_awaited_once_with("Голос учтён")
                self.assertEqual(message.edit_text.await_count, 2)
                text = message.edit_text.call_args.args[0]
                self.assertIn("Сейчас: Лютик украл микрофон", text)
                self.assertIn("После репетиции: 0 голосов", text)
                self.assertIn("Лютик украл микрофон: 1 голосов", text)
                self.assertEqual(message.edit_text.call_args.kwargs["reply_markup"], markup)
                message.reply_text.assert_not_awaited()
                self.assertEqual(fun.open_mood()["votes"], {"101": "lyutik"})

    async def test_repeated_mood_vote_ignores_only_unchanged_message_errors(self):
        mood = fun.open_mood()
        fun.vote_mood(101, mood["token"], "tired")
        message = SimpleNamespace(reply_text=AsyncMock(), edit_text=AsyncMock())
        callback = SimpleNamespace(
            callback_query=SimpleNamespace(data=f"fun:mood:{mood['token']}:tired", answer=AsyncMock()),
            effective_chat=SimpleNamespace(id=-1001, type="supergroup"),
            effective_message=message, effective_user=SimpleNamespace(id=101),
        )
        message.edit_text.side_effect = BadRequest("Message is not modified")
        await fun_callback(callback, self.context)
        callback.callback_query.answer.assert_awaited_once_with("Голос учтён")
        self.assertEqual(fun.open_mood()["counts"]["tired"], 1)
        message.reply_text.assert_not_awaited()

        callback.callback_query.answer.reset_mock()
        message.edit_text.side_effect = BadRequest("Message to edit not found")
        await fun_callback(callback, self.context)
        self.assertEqual(callback.callback_query.answer.await_count, 2)
        callback.callback_query.answer.assert_awaited_with(
            "Не удалось сохранить действие. Попробуй позже.", show_alert=True)
        message.reply_text.assert_not_awaited()

    async def test_mood_changes_actual_ai_prompt_and_callback_cannot_target_other_private_game(self):
        mood = fun.open_mood()
        fun.vote_mood(101, mood["token"], "tired")
        msg = update()
        await answer(msg, self.context, "Привет")
        self.assertIn("устал после репетиции", self.state.client.text.call_args.kwargs["system_prompt"])
        game = fun.start_guess(101)
        query = SimpleNamespace(data=f"fun:guess:101:{game['token']}:end", answer=AsyncMock())
        callback = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=202, type="private"),
                                   effective_message=SimpleNamespace(reply_text=AsyncMock()), effective_user=SimpleNamespace(id=202))
        await fun_callback(callback, self.context)
        self.assertFalse(fun.guess_game(101)["finished"])
        query.answer.assert_awaited_once_with("Кнопка недоступна", show_alert=True)

    async def test_storage_failure_returns_no_fake_success_card(self):
        self.client.fail_write = True
        msg = update()
        await passport_command(msg, self.context)
        self.assertIn("Не удалось", msg.message.reply_text.call_args.args[0])
        self.assertIsNone(self.client.body)
