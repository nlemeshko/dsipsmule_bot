"""Music recommendations with a cached Last.fm pool and an offline fallback."""

import logging
import os
import random
import time
from html import escape
from threading import Lock
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)
LASTFM_URL = 'https://ws.audioscrobbler.com/2.0/'
# Preserve the existing integration; a personal key can override it in Secret env.
DEFAULT_LASTFM_KEY = 'b25b959554ed76058ac220b7b2e0a026'
FALLBACK_SONGS = (
    ('Кукушка', 'Кино'), ('Звезда по имени Солнце', 'Кино'),
    ('Мой рок-н-ролл', 'Би-2'), ('Выхода нет', 'Сплин'),
    ('Искала', 'Земфира'), ('Знаешь ли ты', 'МакSим'),
    ('Лететь', 'Амега'), ('Вахтёрам', 'Бумбокс'),
)
_lock = Lock()
_tracks = []
_cache_key = None
_retry_at = 0


def https_url(value, base=''):
    if not isinstance(value, str) or not value.strip():
        return ''
    value = value.strip()
    if base:
        value = urljoin(base, value)
    elif value.startswith('//'):
        value = 'https:' + value
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        return ''
    return urlunsplit(('https', parts.netloc, parts.path, parts.query, parts.fragment))


def song_message(label, title, artist, link):
    message = f'{label}\n\n<b>{escape(str(title), quote=False)}</b>\nИсполнитель: {escape(str(artist), quote=False)}'
    link = https_url(link)
    if link:
        message += '\n\n' + escape(link, quote=False)
    return message


def get_random_russian_song():
    global _tracks, _cache_key, _retry_at
    key = os.getenv('LASTFM_API_KEY', '').strip() or DEFAULT_LASTFM_KEY
    with _lock:
        now = time.monotonic()
        if key != _cache_key:
            _tracks, _retry_at, _cache_key = [], 0, key
        if now >= _retry_at:
            try:
                response = requests.get(LASTFM_URL, params={
                    'method': 'tag.getTopTracks', 'tag': 'russian', 'api_key': key,
                    'format': 'json', 'limit': 100,
                }, timeout=(3, 6))
                response.raise_for_status()
                data = response.json()
                if data.get('error'):
                    raise ValueError('Last.fm API error')
                candidates = []
                for track in data.get('tracks', {}).get('track', []):
                    title = track.get('name')
                    artist = track.get('artist', {}).get('name')
                    link = https_url(track.get('url'))
                    if isinstance(title, str) and title.strip() and isinstance(artist, str) and artist.strip() and link:
                        candidates.append((title, artist, link))
                if not candidates:
                    raise ValueError('Last.fm returned no usable tracks')
                _tracks = candidates
                _retry_at = now + 3600
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                logger.warning('Last.fm unavailable; using cached recommendations or local selection (%s)', type(exc).__name__)
                _retry_at = now + 60
        if _tracks:
            return random.choice(_tracks)
    title, artist = random.choice(FALLBACK_SONGS)
    return title, artist, 'https://www.youtube.com/results?' + urlencode({'search_query': f'{artist} {title}'})


def smule_song(data):
    songs = data.get('list', [])
    if not isinstance(songs, list):
        raise ValueError('Invalid Smule list')
    candidates = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        link = https_url(song.get('web_url'), 'https://www.smule.com/')
        title = song.get('title')
        if not isinstance(title, str) or not title.strip() or not link:
            continue
        artist = song.get('artist') or ''
        if not isinstance(artist, str):
            artist = ''
        cover = https_url(song.get('cover_url'), 'https://www.smule.com/')
        candidates.append((title, artist, link, cover))
    if not candidates:
        raise ValueError('Smule returned no usable songs')
    return random.choice(candidates)
