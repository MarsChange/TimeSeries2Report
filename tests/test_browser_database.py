"""Browser seeding preserves visitor data while loading the published test case."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3
import tempfile
import unittest
import utils.db_utils as db

SAMPLE = Path(__file__).resolve().parents[1] / 'app.db'


class BrowserDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'app.db'
        self.state = SimpleNamespace()
        self.patches = [patch.object(db, '_thread_local', self.state), patch.object(db, 'get_db_path', return_value=str(self.db_path))]
        for p in self.patches:
            p.start()
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        self.conn.close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def seed(self):
        db._seed_browser_test_database(self.conn, SAMPLE)

    def test_first_launch_matches_published_report(self):
        self.seed()
        with sqlite3.connect(SAMPLE) as original:
            for table in ('sessions', 'messages', 'analysis_results'):
                expected = original.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                actual = self.conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                self.assertEqual(expected, actual)

    def test_empty_earlier_version_is_seeded_only_once(self):
        db.create_session('Session 1')
        self.seed()
        self.assertTrue(self.conn.execute('SELECT 1 FROM analysis_results').fetchone())
        self.conn.execute('DELETE FROM messages')
        self.conn.execute('DELETE FROM analysis_results')
        self.conn.commit()
        self.seed()
        self.assertIsNone(self.conn.execute('SELECT 1 FROM analysis_results').fetchone())

    def test_existing_visitor_data_is_preserved(self):
        db.create_session('Visitor session')
        db.add_message('Visitor session', 'user', 'visitor text')
        self.seed()
        self.assertEqual(db.get_messages('Visitor session')[0]['content'], 'visitor text')
        self.assertIsNone(self.conn.execute('SELECT 1 FROM analysis_results').fetchone())


if __name__ == '__main__':
    unittest.main()
