import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import requests
from telegram.error import BadRequest
from commands import music, entertainment, callback_handler
from commands.hall import hall_command, vote_command


class MusicSourceTests(unittest.TestCase):
    def setUp(self):
        music._tracks, music._cache_key, music._retry_at = [], None, 0
        env = patch.dict(os.environ, {'LASTFM_API_KEY': 'test-key'})
        env.start()
        self.addCleanup(env.stop)

    def response(self, data):
        return Mock(json=Mock(return_value=data), raise_for_status=Mock())

    def test_lastfm_uses_https_and_cached_track_pool(self):
        response = self.response({'tracks': {'track': [{'name': 'Песня', 'artist': {'name': 'Автор'},
                                                       'url': 'http://last.fm/music/song'}]}})
        with patch.object(music.requests, 'get', return_value=response) as get:
            self.assertEqual(music.get_random_russian_song(), ('Песня', 'Автор', 'https://last.fm/music/song'))
            music.get_random_russian_song()
            get.assert_called_once()
            self.assertTrue(get.call_args.args[0].startswith('https://'))
            self.assertEqual(get.call_args.kwargs['params']['api_key'], 'test-key')

    def test_api_errors_empty_and_malformed_responses_have_a_working_fallback(self):
        cases = [{'error': 10}, {'error': 29}, {'tracks': {'track': []}}, {'tracks': {'track': [{'name': 'only title'}]}},
                 {'tracks': None}, ['not a dictionary']]
        for data in cases:
            music._tracks, music._cache_key, music._retry_at = [], None, 0
            with self.subTest(data=data), patch.object(music.requests, 'get', return_value=self.response(data)):
                title, artist, link = music.get_random_russian_song()
                self.assertTrue(title and artist)
                self.assertTrue(link.startswith('https://www.youtube.com/results?'))

    def test_network_failure_uses_last_good_list_and_backs_off(self):
        track = ('Песня', 'Автор', 'https://last.fm/music/song')
        music._tracks, music._cache_key, music._retry_at = [track], 'test-key', 0
        with patch.object(music.requests, 'get', side_effect=requests.Timeout()) as get:
            self.assertEqual(music.get_random_russian_song(), track)
            self.assertEqual(music.get_random_russian_song(), track)
            get.assert_called_once()

    def test_smule_rejects_entries_without_playable_links(self):
        with self.assertRaises(ValueError):
            music.smule_song({'list': [{'title': 'Broken', 'web_url': 'javascript:alert(1)'}]})

    def test_smule_http_failure_is_not_retried_on_every_click(self):
        callback_handler._smule_source, callback_handler._smule_retry_at = None, 0
        session = Mock()
        session.get.return_value.raise_for_status.side_effect = requests.HTTPError('403')
        manager = Mock(__enter__=Mock(return_value=session), __exit__=Mock(return_value=False))
        with patch.object(callback_handler.requests, 'Session', return_value=manager):
            with self.assertRaises(requests.HTTPError):
                callback_handler.fetch_song_of_the_day()
            with self.assertRaises(RuntimeError):
                callback_handler.fetch_song_of_the_day()
        session.get.assert_called_once()
        callback_handler._smule_source, callback_handler._smule_retry_at = None, 0


class MusicAndHallHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        callback_handler.last_song_day_time.clear()
        entertainment.last_russong_time.clear()
        self.bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
        self.context = SimpleNamespace(bot=self.bot)
        self.user = SimpleNamespace(id=501, username='singer')
        self.message = SimpleNamespace(text='', reply_text=AsyncMock(), reply_photo=AsyncMock())
        self.update = SimpleNamespace(effective_user=self.user, message=self.message,
            callback_query=SimpleNamespace(data='button4', answer=AsyncMock(), from_user=self.user,
                                           message=SimpleNamespace(chat=SimpleNamespace(id=501))))

    async def test_random_song_escapes_telegram_html_and_keeps_https_link(self):
        with patch.object(entertainment, 'get_random_russian_song', return_value=('A < B & C', 'R&B', 'http://example.com/?a=1&b=2')):
            await entertainment.random_command(self.update, self.context)
        message = self.message.reply_text.call_args.args[0]
        self.assertIn('A &lt; B &amp; C', message)
        self.assertIn('R&amp;B', message)
        self.assertIn('https://example.com/', message)

    async def test_failed_song_cover_sends_same_song_as_text(self):
        self.bot.send_photo.side_effect = BadRequest('Invalid image')
        data = {'list': [{'title': 'Оригинал <3', 'artist': 'R&B', 'web_url': '/song', 'cover_url': '//example.com/cover.jpg'}]}
        with patch.object(callback_handler, 'fetch_song_of_the_day', return_value=data), \
             patch.object(callback_handler, 'get_random_russian_song') as fallback:
            await callback_handler.handle_callback_query(self.update, self.context)
        fallback.assert_not_called()
        message = self.bot.send_message.call_args.args[1]
        self.assertIn('Оригинал &lt;3', message)
        self.assertIn('https://www.smule.com/song', message)

    async def test_smule_403_uses_fallback_song(self):
        with patch.object(callback_handler, 'fetch_song_of_the_day', side_effect=requests.HTTPError()), \
             patch.object(callback_handler, 'get_random_russian_song', return_value=('Запасная', 'Автор', 'https://example.com/song')):
            await callback_handler.handle_callback_query(self.update, self.context)
        self.assertIn('Запасная', self.bot.send_message.call_args.args[1])
        self.bot.send_photo.assert_not_called()

    async def test_failed_s3_write_is_not_acknowledged_as_saved_by_handlers(self):
        for text, handler in [('/hall legend test', hall_command), ('/vote legend test', vote_command)]:
            self.message.text = text
            self.message.reply_text.reset_mock()
            with patch('commands.hall.update_hall_data', side_effect=OSError('storage down')):
                await handler(self.update, self.context)
            self.assertIn('Не удалось сохранить', self.message.reply_text.call_args.args[0])
            self.message.reply_photo.assert_not_called()
