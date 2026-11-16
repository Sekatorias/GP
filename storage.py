"""Локальные и переживающие перезапуск настройки. Сохраните БД при переносе VPS."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

DB_PATH = Path(os.environ.get("GP_DB_PATH", "data/gp.sqlite3"))
MSK = ZoneInfo("Europe/Moscow")


def now_msk():
    return datetime.now(MSK)


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(guild_id):
    # Изменяем таблицы в пределах v3 без произвольного внешнего конфига.
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            interval_days INTEGER NOT NULL DEFAULT 3,
            hour INTEGER NOT NULL DEFAULT 0,
            minute INTEGER NOT NULL DEFAULT 0,
            anchor_date TEXT NOT NULL DEFAULT '2026-11-17',
            explicit_percent INTEGER NOT NULL DEFAULT 45,
            announce_channel_id INTEGER,
            announce_enabled INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_scheduled_date TEXT,
            last_name TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            changed_at TEXT NOT NULL,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            announce_ok INTEGER NOT NULL DEFAULT 0
        )""")
        default_channel = os.environ.get("DISCORD_ANNOUNCE_CHANNEL_ID")
        channel = int(default_channel) if default_channel and default_channel.isdigit() else None
        db.execute("INSERT OR IGNORE INTO settings (guild_id, announce_channel_id) VALUES (?, ?)",
                   (guild_id, channel))


def get(guild_id):
    with connect() as db:
        row = db.execute("SELECT * FROM settings WHERE guild_id = ?", (guild_id,)).fetchone()
        if row is None:
            raise RuntimeError("Нет записи настроек; сначала запусти init()")
        return dict(row)


ALLOWED_COLUMNS = frozenset({"interval_days", "hour", "minute", "anchor_date", "explicit_percent",
                             "announce_channel_id", "announce_enabled", "enabled", "last_scheduled_date",
                             "last_name"})


def change(guild_id, **values):
    if not values or any(key not in ALLOWED_COLUMNS for key in values):
        raise ValueError("Недопустимые настройки")
    clause = ", ".join(f"{key} = ?" for key in values)
    with connect() as db:
        db.execute(f"UPDATE settings SET {clause} WHERE guild_id = ?",
                   (*values.values(), guild_id))


def record(guild_id, name, mode, scheduled_date=None):
    with connect() as db:
        db.execute("INSERT INTO history (guild_id, changed_at, name, mode) VALUES (?, ?, ?, ?)",
                   (guild_id, now_msk().isoformat(), name, mode))
        if scheduled_date:
            db.execute("UPDATE settings SET last_name = ?, last_scheduled_date = ? WHERE guild_id = ?",
                       (name, scheduled_date, guild_id))
        else:
            db.execute("UPDATE settings SET last_name = ? WHERE guild_id = ?", (name, guild_id))
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def announcement_ok(record_id):
    with connect() as db:
        db.execute("UPDATE history SET announce_ok = 1 WHERE id = ?", (record_id,))


def rename_count(guild_id):
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM history WHERE guild_id = ?", (guild_id,)).fetchone()[0]


def next_slot(config, now=None, including_now=False):
    """Ближайший интервал начиная с указанной якорной даты.

    При запуске после пропуска даты возвращает ближайшую будущую дату.
    """
    now = now or now_msk()
    anchor = date.fromisoformat(config["anchor_date"])
    n = int(config["interval_days"])
    candidate = datetime.combine(anchor, datetime.min.time(), tzinfo=MSK)
    candidate = candidate.replace(hour=config["hour"], minute=config["minute"])
    if (candidate > now) or (including_now and candidate == now):
        return candidate
    elapsed = (now.date() - anchor).days
    steps = max(0, elapsed // n)
    candidate += timedelta(days=steps * n)
    if candidate <= now and not (including_now and candidate == now):
        candidate += timedelta(days=n)
    return candidate


def scheduled_today(config, now=None):
    now = now or now_msk()
    start = date.fromisoformat(config["anchor_date"])
    diff = (now.date() - start).days
    if diff < 0 or diff % int(config["interval_days"]) != 0:
        return False
    return (now.hour, now.minute) >= (config["hour"], config["minute"])
