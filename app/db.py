import os
import sqlite3
import time

DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "memory.sqlite")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")


def _migrate_legacy_messages(conn):
    """Sai da frente de um banco da versao antiga (memoria por usuario, sem canal).

    A tabela `messages` original nao tinha channel_id, e `CREATE TABLE IF NOT EXISTS`
    nao corrige tabela existente - o schema novo falhava ao criar os indices com um
    erro seco de "no such column: channel_id" e o bot nem subia. Aqui a tabela antiga
    e renomeada (nada e apagado, os dados continuam consultaveis) para a nova ser
    criada limpa. Nao ha como deduzir o canal das linhas antigas, entao elas nao sao
    convertidas.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'"
    ).fetchone()
    if not exists:
        return

    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "channel_id" in columns:
        return

    suffix = 1
    while conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (f"messages_legacy_v{suffix}",),
    ).fetchone():
        suffix += 1
    legacy_name = f"messages_legacy_v{suffix}"

    # Os indices acompanham a tabela renomeada e continuariam ocupando os nomes que o
    # schema novo usa, fazendo o CREATE INDEX IF NOT EXISTS ser silenciosamente ignorado.
    for (index_name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='messages' "
        "AND name LIKE 'idx_messages%'"
    ).fetchall():
        conn.execute(f"DROP INDEX IF EXISTS {index_name}")

    conn.execute(f"ALTER TABLE messages RENAME TO {legacy_name}")
    conn.commit()
    moved = conn.execute(f"SELECT COUNT(*) FROM {legacy_name}").fetchone()[0]
    print(
        f"[db] Banco da versao antiga detectado: tabela 'messages' ({moved} linhas, sem "
        f"channel_id) preservada como '{legacy_name}'. O historico comeca vazio, a "
        "memoria agora e por canal."
    )


_migrate_legacy_messages(_conn)

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
    -- Memoria de longo prazo: fatos que sobrevivem a rotacao do historico e ao reset
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
    -- Lembretes agendados. Ficam no banco (e nao em memoria) para sobreviverem a
    -- restart do container: o loop de entrega recupera os vencidos ao subir.
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        username TEXT,
        text TEXT NOT NULL,
        remind_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(delivered, remind_at);
    CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, delivered);
    -- Canais em que o bot foi mandado calar a boca com o comando parar. So usado em
    -- DM, onde ele responderia tudo por padrao; em canal o parar apenas encerra a
    -- janela de follow-up, sem silenciar o bot para os outros.
    CREATE TABLE IF NOT EXISTS muted_channels (
        channel_id TEXT PRIMARY KEY,
        muted_at INTEGER NOT NULL
    );
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


# --- Modo silencioso ---


def set_muted(channel_id, muted):
    if muted:
        _conn.execute(
            "INSERT INTO muted_channels (channel_id, muted_at) VALUES (?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET muted_at = excluded.muted_at",
            (channel_id, _now_ms()),
        )
    else:
        _conn.execute("DELETE FROM muted_channels WHERE channel_id = ?", (channel_id,))
    _conn.commit()


def is_muted(channel_id):
    row = _conn.execute(
        "SELECT 1 FROM muted_channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row is not None


# --- Lembretes ---


def count_pending_reminders(user_id):
    row = _conn.execute(
        "SELECT COUNT(*) FROM reminders WHERE user_id = ? AND delivered = 0", (user_id,)
    ).fetchone()
    return row[0] if row else 0


def add_reminder(channel_id, user_id, username, text, remind_at):
    cursor = _conn.execute(
        "INSERT INTO reminders (channel_id, user_id, username, text, remind_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, user_id, username, text, remind_at, _now_ms()),
    )
    _conn.commit()
    return cursor.lastrowid


def get_due_reminders(now):
    rows = _conn.execute(
        "SELECT id, channel_id, user_id, username, text, remind_at FROM reminders "
        "WHERE delivered = 0 AND remind_at <= ? ORDER BY remind_at",
        (now,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "channel_id": r[1],
            "user_id": r[2],
            "username": r[3],
            "text": r[4],
            "remind_at": r[5],
        }
        for r in rows
    ]


def get_pending_reminders(channel_id=None, user_id=None):
    """Lembretes ainda nao entregues, filtrando por canal e/ou usuario."""
    clauses = ["delivered = 0"]
    params = []
    if channel_id is not None:
        clauses.append("channel_id = ?")
        params.append(channel_id)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)

    rows = _conn.execute(
        "SELECT id, channel_id, user_id, username, text, remind_at FROM reminders "
        f"WHERE {' AND '.join(clauses)} ORDER BY remind_at",
        params,
    ).fetchall()
    return [
        {
            "id": r[0],
            "channel_id": r[1],
            "user_id": r[2],
            "username": r[3],
            "text": r[4],
            "remind_at": r[5],
        }
        for r in rows
    ]


def mark_reminder_delivered(reminder_id):
    _conn.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
    _conn.commit()


def cancel_reminder(reminder_id, user_id):
    """Cancela um lembrete, mas so se ele for da propria pessoa."""
    cursor = _conn.execute(
        "DELETE FROM reminders WHERE id = ? AND user_id = ? AND delivered = 0",
        (reminder_id, user_id),
    )
    _conn.commit()
    return cursor.rowcount > 0


def purge_old_reminders(before):
    """Limpa lembretes ja entregues e antigos, para a tabela nao crescer para sempre."""
    cursor = _conn.execute(
        "DELETE FROM reminders WHERE delivered = 1 AND remind_at < ?", (before,)
    )
    _conn.commit()
    return cursor.rowcount
