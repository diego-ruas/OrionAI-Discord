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
    CREATE TABLE IF NOT EXISTS channel_settings (
        channel_id TEXT PRIMARY KEY,
        persona TEXT NOT NULL
    );
    -- Memoria de longo prazo: fatos que sobrevivem a rotacao do historico e ao !reset
    -- de mensagens. Escritos pelo modelo via ferramenta remember_fact.
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL,
        subject TEXT,
        fact TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_facts_channel ON facts(channel_id, id);
    -- Mensagens do canal em que o bot nao foi chamado, guardadas apenas como contexto
    -- ("do que estavam falando") para quando ele for chamado. Rotativas e curtas.
    CREATE TABLE IF NOT EXISTS ambient_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL,
        username TEXT,
        content TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ambient_channel ON ambient_messages(channel_id, id);
    """
)
_conn.commit()


def _now_ms():
    return int(time.time() * 1000)


def add_message(channel_id, user_id, username, role, content, max_messages):
    _conn.execute(
        "INSERT INTO messages (channel_id, user_id, username, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, user_id, username, role, content, _now_ms()),
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


def count_messages(channel_id):
    row = _conn.execute(
        "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row[0] if row else 0


def clear_history(channel_id):
    _conn.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))
    _conn.execute("DELETE FROM ambient_messages WHERE channel_id = ?", (channel_id,))
    _conn.commit()


def get_persona(channel_id):
    row = _conn.execute(
        "SELECT persona FROM channel_settings WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row[0] if row else None


def set_persona(channel_id, persona_key):
    _conn.execute(
        "INSERT INTO channel_settings (channel_id, persona) VALUES (?, ?) "
        "ON CONFLICT(channel_id) DO UPDATE SET persona = excluded.persona",
        (channel_id, persona_key),
    )
    _conn.commit()


# --- Memoria de longo prazo (fatos) ---


def add_fact(channel_id, subject, fact, max_facts):
    """Salva um fato. Ignora duplicata exata. Retorna True se salvou de fato."""
    fact = (fact or "").strip()
    if not fact:
        return False

    existing = _conn.execute(
        "SELECT id FROM facts WHERE channel_id = ? AND lower(fact) = lower(?)",
        (channel_id, fact),
    ).fetchone()
    if existing:
        return False

    _conn.execute(
        "INSERT INTO facts (channel_id, subject, fact, created_at) VALUES (?, ?, ?, ?)",
        (channel_id, (subject or "").strip() or None, fact, _now_ms()),
    )
    # Mantem apenas os mais recentes, pra memoria nao crescer sem limite nem estourar
    # o prompt de sistema.
    _conn.execute(
        """
        DELETE FROM facts WHERE channel_id = ? AND id NOT IN (
            SELECT id FROM facts WHERE channel_id = ? ORDER BY id DESC LIMIT ?
        )
        """,
        (channel_id, channel_id, max_facts),
    )
    _conn.commit()
    return True


def get_facts(channel_id):
    rows = _conn.execute(
        "SELECT id, subject, fact FROM facts WHERE channel_id = ? ORDER BY id",
        (channel_id,),
    ).fetchall()
    return [{"id": r[0], "subject": r[1], "fact": r[2]} for r in rows]


def forget_facts(channel_id, query):
    """Apaga fatos que contenham o texto buscado. Retorna quantos foram apagados."""
    query = (query or "").strip()
    if not query:
        return 0

    cursor = _conn.execute(
        "DELETE FROM facts WHERE channel_id = ? AND "
        "(fact LIKE ? COLLATE NOCASE OR subject LIKE ? COLLATE NOCASE)",
        (channel_id, f"%{query}%", f"%{query}%"),
    )
    _conn.commit()
    return cursor.rowcount


def delete_fact(channel_id, fact_id):
    cursor = _conn.execute(
        "DELETE FROM facts WHERE channel_id = ? AND id = ?", (channel_id, fact_id)
    )
    _conn.commit()
    return cursor.rowcount > 0


def clear_facts(channel_id):
    cursor = _conn.execute("DELETE FROM facts WHERE channel_id = ?", (channel_id,))
    _conn.commit()
    return cursor.rowcount


# --- Contexto ambiente (conversa do canal sem o bot) ---


def add_ambient_message(channel_id, username, content, max_messages):
    if max_messages <= 0:
        return

    _conn.execute(
        "INSERT INTO ambient_messages (channel_id, username, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (channel_id, username, content, _now_ms()),
    )
    _conn.execute(
        """
        DELETE FROM ambient_messages WHERE channel_id = ? AND id NOT IN (
            SELECT id FROM ambient_messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?
        )
        """,
        (channel_id, channel_id, max_messages),
    )
    _conn.commit()


def get_ambient_messages(channel_id, max_messages):
    if max_messages <= 0:
        return []

    rows = _conn.execute(
        "SELECT username, content FROM ambient_messages WHERE channel_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (channel_id, max_messages),
    ).fetchall()
    rows.reverse()
    return [{"username": r[0] or "alguem", "content": r[1]} for r in rows]


def clear_ambient_messages(channel_id):
    _conn.execute("DELETE FROM ambient_messages WHERE channel_id = ?", (channel_id,))
    _conn.commit()
