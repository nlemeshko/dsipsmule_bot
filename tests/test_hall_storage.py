import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from botocore.exceptions import ClientError
from storage import hall


class FakeS3:
    def __init__(self, body=None):
        self.body = body
        self.fail_read = False
        self.fail_write = False
        self.writes = 0

    def get_object(self, **kwargs):
        if self.fail_read:
            raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'GetObject')
        if self.body is None:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.body)}

    def put_object(self, **kwargs):
        if self.fail_write:
            raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'PutObject')
        self.body = kwargs['Body']
        self.writes += 1


class HallStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {'DATA_DIR': self.directory.name}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.rows = [{'category': 'legend', 'name': '@singer', 'nominated_by': 'admin',
                      'date': '2026-10-05', 'votes': '1'}]
        self.client = FakeS3()
        storage = patch.object(hall, 's3_storage', return_value=(self.client, 'bucket', 'dsipsmule-bot/hall/hall.csv'))
        storage.start()
        self.addCleanup(storage.stop)

    def test_s3_restores_rows_after_local_disk_is_lost(self):
        hall.save_hall_data(self.rows)
        hall.hall_path().unlink()
        self.assertEqual(hall.load_hall_data(), self.rows)

    def test_failed_s3_write_does_not_update_local_cache(self):
        hall.save_hall_data(self.rows)
        self.client.fail_write = True
        changed = [dict(self.rows[0], votes='9')]
        with self.assertRaises(ClientError):
            hall.save_hall_data(changed)
        self.assertEqual(hall._decode(hall.hall_path().read_bytes()), self.rows)
        self.assertEqual(hall.load_hall_data(), self.rows)

    def test_failed_read_never_overwrites_authoritative_data(self):
        hall.save_hall_data(self.rows)
        self.client.fail_read = True
        with self.assertRaises(ClientError):
            hall.update_hall_data(lambda rows: (True, rows.append(dict(self.rows[0], name='other'))))
        self.assertEqual(self.client.writes, 1)

    def test_initialization_migrates_local_csv_without_overwriting_existing_s3(self):
        hall.hall_path().write_bytes(hall._encode(self.rows))
        hall.initialize_hall_storage()
        self.assertEqual(hall.load_hall_data(), self.rows)
        hall.hall_path().write_bytes(hall._encode([]))
        hall.initialize_hall_storage()
        self.assertEqual(hall.load_hall_data(), self.rows)
        self.assertEqual(self.client.writes, 1)

    def test_unwritable_cache_does_not_undo_durable_s3_write(self):
        with patch.object(hall, '_cache', side_effect=OSError('read-only')):
            hall.save_hall_data(self.rows)
        self.assertEqual(hall.load_hall_data(), self.rows)

    def test_concurrent_votes_do_not_get_lost(self):
        hall.save_hall_data(self.rows)

        def vote(rows):
            rows[0]['votes'] = str(int(rows[0]['votes']) + 1)
            return True, None

        with ThreadPoolExecutor(max_workers=8) as workers:
            list(workers.map(lambda _: hall.update_hall_data(vote), range(40)))
        self.assertEqual(hall.load_hall_data()[0]['votes'], '41')

    def test_corrupt_remote_file_is_not_replaced_with_local_seed(self):
        self.client.body = b'<html>error</html>'
        with self.assertRaises(ValueError):
            hall.initialize_hall_storage()
        self.assertEqual(self.client.writes, 0)

    def test_local_mode_still_works_without_s3(self):
        with patch.object(hall, 's3_storage', return_value=None):
            hall.save_hall_data(self.rows)
            self.assertEqual(hall.load_hall_data(), self.rows)

class ConfigurationTests(unittest.TestCase):
    def test_missing_bucket_or_credentials_is_an_error(self):
        for env in [{'S3_ACCESS_KEY_ID': 'example'}, {'S3_BUCKET': 'bucket'}]:
            with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                hall.s3_storage()

    def test_no_s3_configuration_uses_local_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(hall.s3_storage())
