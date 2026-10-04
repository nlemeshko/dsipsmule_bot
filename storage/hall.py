"""CSV hall storage. S3 is authoritative when configured; local disk is a cache."""

import csv
import logging
import os
import tempfile
from functools import lru_cache
from io import StringIO
from pathlib import Path
from threading import RLock

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
FIELDS = ['category', 'name', 'nominated_by', 'date', 'votes']
BASE = Path(__file__).resolve().parent.parent
MAX_CSV = 4 * 1024 * 1024
LOCK = RLock()


def hall_path():
    return Path(os.getenv('DATA_DIR', str(BASE / 'data'))) / 'hall.csv'


@lru_cache(maxsize=4)
def _client(endpoint, region, access_key, secret_key):
    return boto3.client(
        's3', endpoint_url=endpoint, region_name=region,
        aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=15,
                      retries={'mode': 'standard', 'max_attempts': 2},
                      request_checksum_calculation='when_required',
                      response_checksum_validation='when_required'),
    )


def s3_storage():
    bucket = os.getenv('S3_BUCKET', '').strip()
    access = os.getenv('S3_ACCESS_KEY_ID', '') or os.getenv('AWS_ACCESS_KEY_ID', '')
    secret = os.getenv('S3_SECRET_ACCESS_KEY', '') or os.getenv('AWS_SECRET_ACCESS_KEY', '')
    if not bucket:
        if access or secret:
            raise ValueError('Для сохранения зала славы задайте S3_BUCKET')
        return None
    if not access or not secret:
        raise ValueError('Для S3 задайте S3_ACCESS_KEY_ID и S3_SECRET_ACCESS_KEY')
    endpoint = os.getenv('S3_ENDPOINT_URL', 'https://nbg1.your-objectstorage.com').strip().rstrip('/')
    if not endpoint.startswith('https://'):
        raise ValueError('S3_ENDPOINT_URL должен использовать HTTPS')
    key = os.getenv('HALL_S3_KEY', 'dsipsmule-bot/hall/hall.csv').strip()
    if not key:
        raise ValueError('HALL_S3_KEY не должен быть пустым')
    client = _client(endpoint, os.getenv('S3_REGION', 'nbg1'), access, secret)
    return client, bucket, key


def _decode(content):
    if len(content) > MAX_CSV:
        raise ValueError('Файл зала славы слишком большой')
    reader = csv.DictReader(StringIO(content.decode('utf-8-sig'), newline=''))
    if reader.fieldnames != FIELDS:
        raise ValueError('Файл зала славы имеет неправильный формат')
    rows = list(reader)
    for row in rows:
        if set(row) != set(FIELDS) or any(value is None for value in row.values()):
            raise ValueError('Повреждена строка зала славы')
        if row['category'] not in {'legend', 'cringe'} or not row['name'].strip() or int(row['votes']) < 0:
            raise ValueError('Повреждены данные зала славы')
    return rows


def _encode(rows):
    output = StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    content = output.getvalue().encode('utf-8')
    _decode(content)
    return content


def _local_data():
    path = hall_path()
    if not path.exists() and os.getenv('DATA_DIR'):
        path = BASE / 'data' / 'hall.csv'
    try:
        return _decode(path.read_bytes())
    except FileNotFoundError:
        return []


def _cache(content):
    path = hall_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _remote_data(storage):
    client, bucket, key = storage
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'NoSuchKey', 'NotFound'}:
            return None
        raise
    with response['Body'] as stream:
        return _decode(stream.read(MAX_CSV + 1))


def load_hall_data():
    with LOCK:
        storage = s3_storage()
        if storage:
            rows = _remote_data(storage)
            if rows is not None:
                return rows
        return _local_data()


def save_hall_data(rows):
    with LOCK:
        content = _encode(rows)
        storage = s3_storage()
        if storage:
            client, bucket, key = storage
            # Never acknowledge a local-only write when S3 is configured.
            client.put_object(Bucket=bucket, Key=key, Body=content, ContentType='text/csv; charset=utf-8')
            try:
                _cache(content)
            except OSError:
                logger.warning('Hall saved in S3; local cache could not be updated')
        else:
            _cache(content)


def update_hall_data(change):
    # Serialize read-modify-write across all users, group chat and Mini App.
    with LOCK:
        rows = load_hall_data()
        changed, result = change(rows)
        if changed:
            save_hall_data(rows)
        return result


def initialize_hall_storage():
    with LOCK:
        storage = s3_storage()
        if storage and _remote_data(storage) is None:
            save_hall_data(_local_data())
