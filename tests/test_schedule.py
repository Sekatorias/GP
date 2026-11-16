import os
from datetime import datetime, date
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / 'config.sqlite3'
        self.guild = 123456
        storage.init(self.guild)

    def tearDown(self):
        storage.DB_PATH = self.old
        self.temp.cleanup()

    def t(self, d, h=0, m=0):
        return datetime.fromisoformat(f'{d}T{h:02d}:{m:02d}:00').replace(tzinfo=ZoneInfo('Europe/Moscow'))

    def test_default_and_persistence(self):
        s = storage.get(self.guild)
        self.assertEqual(s['interval_days'], 3)
        storage.change(self.guild, interval_days=7, explicit_percent=75, hour=19, minute=40)
        s = storage.get(self.guild)
        self.assertEqual((s['interval_days'], s['explicit_percent'], s['hour'], s['minute']),
                         (7, 75, 19, 40))

    def test_every_three_days_cross_month(self):
        s = storage.get(self.guild)
        self.assertTrue(storage.scheduled_today(s, self.t('2026-11-17', 0, 1)))
        self.assertFalse(storage.scheduled_today(s, self.t('2026-11-18', 5)))
        self.assertTrue(storage.scheduled_today(s, self.t('2026-11-20', 5)))
        self.assertFalse(storage.scheduled_today(s, self.t('2026-11-30', 5)))
        self.assertTrue(storage.scheduled_today(s, self.t('2026-12-02', 5)))
        self.assertEqual(storage.next_slot(s, self.t('2026-11-29', 12)).date(), date(2026, 12, 2))
        self.assertEqual(storage.next_slot(s, self.t('2026-11-16', 12)).date(), date(2026, 11, 17))

    def test_time_gate_and_next_slot(self):
        storage.change(self.guild, hour=18, minute=30)
        s = storage.get(self.guild)
        self.assertFalse(storage.scheduled_today(s, self.t('2026-11-17', 18, 29)))
        self.assertTrue(storage.scheduled_today(s, self.t('2026-11-17', 18, 30)))
        self.assertEqual(storage.next_slot(s, self.t('2026-11-17', 18, 31)).date(), date(2026, 11, 20))

    def test_record_and_mark_date(self):
        ident = storage.record(self.guild, 'Грустный пингвин', 'scheduled', '2026-11-17')
        storage.announcement_ok(ident)
        s = storage.get(self.guild)
        self.assertEqual(s['last_name'], 'Грустный пингвин')
        self.assertEqual(s['last_scheduled_date'], '2026-11-17')
        self.assertEqual(storage.rename_count(self.guild), 1)


if __name__ == '__main__':
    unittest.main()
