import os
import sqlite3
import time

DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "memory.sqlite")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        username TEXT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, id);
    CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);
    """
)
_conn.commit()


def add_message(channel_id, user_id, username, role, content, max_messages):
    _conn.execute(
        "INSERT INTO messages (channel_id, user_id, username, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, user_id, username, role, content, int(time.time() * 1000)),
    )
    _conn.execute(
        """
        DELETE FROM messages WHERE channel_id = ? AND id NOT IN (
            SELECT id FROM messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?
        )
        """,
        (channel_id, channel_id, max_messages),
    )
    _conn.commit()


def get_history(channel_id, max_messages):
    rows = _conn.execute(
        "SELECT user_id, username, role, content FROM messages "
        "WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
        (channel_id, max_messages),
    ).fetchall()
    rows.reverse()
    return [
        {
            "role": r[2],
            "content": r[3],
            "user_id": r[0],
            "username": r[1] or "Unknown",
        }
        for r in rows
    ]


def clear_history(channel_id):
    _conn.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))
    _conn.commit()
