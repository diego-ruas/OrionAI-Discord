import os
import sqlite3
import time

from .utils.safety import escape_like

DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "memory.sqlite")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA synchronous=NORMAL")
_conn.execute("PRAGMA temp_store=MEMORY")


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

    # Os indices acompanham a tabela renomeada e continuaria ocupando os nomes que o
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
        display_name TEXT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, id);
    -- Nenhuma query filtra por user_id; o indice so custava escrita. Indice nao e dado
    -- do usuario, entao dropar e seguro.
    DROP INDEX IF EXISTS idx_messages_user;
    -- Memoria de longo prazo: fatos que sobrevivem a rotacao do historico e ao reset
    -- de mensagens. Escritos pela curadoria em segundo plano (app/memory.py).
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
        display_name TEXT,
        user_id TEXT,
        content TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ambient_channel ON ambient_messages(channel_id, id);
    -- Canais em que o bot foi mandado calar a boca com o comando parar. So usado em
    -- DM, onde ele responderia tudo por padrao; em canal o parar apenas encerra a
    -- janela de follow-up, sem silenciar o bot para os outros.
    CREATE TABLE IF NOT EXISTS muted_channels (
        channel_id TEXT PRIMARY KEY,
        muted_at INTEGER NOT NULL
    );
    -- Resumo rodando da conversa que ja saiu do historico e ate onde a curadoria de
    -- fatos ja leu. Uma linha por canal.
    CREATE TABLE IF NOT EXISTS channel_memory (
        channel_id TEXT PRIMARY KEY,
        summary TEXT NOT NULL DEFAULT '',
        curated_until INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
    );
    -- Pessoas que pediram para o bot nao marca-las. Uma linha por pessoa.
    CREATE TABLE IF NOT EXISTS no_ping (
        user_id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL
    );
    """
)


def _ensure_column(table, column, decl):
    # Coluna nova em banco existente: ADD COLUMN nao toca nos dados.
    if column not in [r[1] for r in _conn.execute(f"PRAGMA table_info({table})")]:
        _conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# Fatos antigos ficam sem autor (NULL) e nao contam para a cota de ninguem; mensagens
# antigas ficam sem apelido e aparecem so pelo @usuario.
_ensure_column("facts", "author_id", "TEXT")
_ensure_column("messages", "display_name", "TEXT")
_ensure_column("ambient_messages", "display_name", "TEXT")
_ensure_column("ambient_messages", "user_id", "TEXT")
_conn.commit()


def _now_ms():
    return int(time.time() * 1000)


def add_message(channel_id, user_id, username, display_name, role, content, max_messages):
    with _conn:
        _conn.execute(
            "INSERT INTO messages (channel_id, user_id, username, display_name, role, content, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (channel_id, user_id, username, display_name, role, content, _now_ms()),
        )
        _conn.execute(
            """
            DELETE FROM messages WHERE channel_id = ? AND id NOT IN (
                SELECT id FROM messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (channel_id, channel_id, max_messages),
        )


def get_history(channel_id, max_messages):
    rows = _conn.execute(
        "SELECT user_id, username, role, content, display_name, created_at FROM messages "
        "WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
        (channel_id, max_messages),
    ).fetchall()
    rows.reverse()
    return [
        {
            "role": r[2],
            "content": r[3],
            "user_id": r[0],
            "username": r[1] or "",
            "display_name": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def count_messages(channel_id):
    row = _conn.execute(
        "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row[0] if row else 0


def clear_history(channel_id):
    with _conn:
        _conn.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))
        _conn.execute("DELETE FROM ambient_messages WHERE channel_id = ?", (channel_id,))
        _conn.execute("DELETE FROM channel_memory WHERE channel_id = ?", (channel_id,))


def _rows_to_dicts(rows):
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "username": r[2] or "",
            "role": r[3],
            "content": r[4],
            "display_name": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def get_messages_after(channel_id, after_id, limit):
    rows = _conn.execute(
        "SELECT id, user_id, username, role, content, display_name, created_at FROM messages "
        "WHERE channel_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
        (channel_id, after_id, limit),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_oldest_messages(channel_id, limit):
    rows = _conn.execute(
        "SELECT id, user_id, username, role, content, display_name, created_at FROM messages "
        "WHERE channel_id = ? ORDER BY id ASC LIMIT ?",
        (channel_id, limit),
    ).fetchall()
    return _rows_to_dicts(rows)


# --- Resumo rodando e progresso da curadoria ---


def get_channel_memory(channel_id):
    row = _conn.execute(
        "SELECT summary, curated_until FROM channel_memory WHERE channel_id = ?",
        (channel_id,),
    ).fetchone()
    if not row:
        return {"summary": "", "curated_until": 0}
    return {"summary": row[0], "curated_until": row[1]}


def fold_into_summary(channel_id, summary, up_to_id):
    """Grava o resumo e apaga as mensagens incorporadas na mesma transacao, para
    nenhuma mensagem sumir sem o resumo ter sido gravado."""
    with _conn:
        _conn.execute(
            "INSERT INTO channel_memory (channel_id, summary, curated_until, updated_at) "
            "VALUES (?, ?, 0, ?) ON CONFLICT(channel_id) DO UPDATE SET "
            "summary = excluded.summary, updated_at = excluded.updated_at",
            (channel_id, summary, _now_ms()),
        )
        _conn.execute(
            "DELETE FROM messages WHERE channel_id = ? AND id <= ?",
            (channel_id, up_to_id),
        )


def set_curated_until(channel_id, message_id):
    with _conn:
        _conn.execute(
            "INSERT INTO channel_memory (channel_id, summary, curated_until, updated_at) "
            "VALUES (?, '', ?, ?) ON CONFLICT(channel_id) DO UPDATE SET "
            "curated_until = excluded.curated_until, updated_at = excluded.updated_at",
            (channel_id, message_id, _now_ms()),
        )


# --- Memoria de longo prazo (fatos) ---


def add_fact(channel_id, subject, fact, max_facts, author_id=None, max_per_author=0):
    """Salva um fato. Retorna True se salvou; False se duplicata, memoria cheia ou
    autor no limite."""
    fact = (fact or "").strip()
    if not fact:
        return False

    existing = _conn.execute(
        "SELECT id FROM facts WHERE channel_id = ? AND lower(fact) = lower(?)",
        (channel_id, fact),
    ).fetchone()
    if existing:
        return False

    with _conn:
        # Rotacao automatica deixava qualquer pessoa expulsar a memoria inteira do
        # canal so enchendo-a; agora so quem modera abre espaco (esquecer).
        count = _conn.execute(
            "SELECT COUNT(*) FROM facts WHERE channel_id = ?", (channel_id,)
        ).fetchone()[0]
        if count >= max_facts:
            return False
        # Cota por autor: sem ela uma pessoa so ocupava todos os espacos do canal.
        if author_id and max_per_author > 0:
            mine = _conn.execute(
                "SELECT COUNT(*) FROM facts WHERE channel_id = ? AND author_id = ?",
                (channel_id, str(author_id)),
            ).fetchone()[0]
            if mine >= max_per_author:
                return False
        _conn.execute(
            "INSERT INTO facts (channel_id, subject, fact, author_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                channel_id,
                (subject or "").strip() or None,
                fact,
                str(author_id) if author_id else None,
                _now_ms(),
            ),
        )
    return True


def get_facts(channel_id):
    rows = _conn.execute(
        "SELECT id, subject, fact FROM facts WHERE channel_id = ? ORDER BY id",
        (channel_id,),
    ).fetchall()
    return [{"id": r[0], "subject": r[1], "fact": r[2]} for r in rows]


def forget_facts(channel_id, query, max_matches=None):
    """Apaga fatos que contenham o texto buscado. Retorna quantos foram apagados, ou
    None (sem apagar nada) se casar com mais de `max_matches` fatos."""
    query = (query or "").strip()
    if not query:
        return 0

    # Curinga do LIKE escapado: sem isso query "%" apagava a memoria inteira.
    pattern = f"%{escape_like(query)}%"
    where = (
        "channel_id = ? AND "
        "(fact LIKE ? ESCAPE '\\' COLLATE NOCASE OR subject LIKE ? ESCAPE '\\' COLLATE NOCASE)"
    )
    params = (channel_id, pattern, pattern)
    with _conn:
        if max_matches is not None:
            found = _conn.execute(f"SELECT COUNT(*) FROM facts WHERE {where}", params).fetchone()[0]
            if found > max_matches:
                return None
        cursor = _conn.execute(f"DELETE FROM facts WHERE {where}", params)
        removed = cursor.rowcount
    return removed


def delete_fact(channel_id, fact_id):
    with _conn:
        cursor = _conn.execute(
            "DELETE FROM facts WHERE channel_id = ? AND id = ?", (channel_id, fact_id)
        )
        removed = cursor.rowcount
    return removed > 0


def clear_facts(channel_id):
    with _conn:
        cursor = _conn.execute("DELETE FROM facts WHERE channel_id = ?", (channel_id,))
        removed = cursor.rowcount
    return removed


# --- Contexto ambiente (conversa do canal sem o bot) ---


def add_ambient_message(channel_id, user_id, username, display_name, content, max_messages):
    if max_messages <= 0:
        return

    with _conn:
        _conn.execute(
            "INSERT INTO ambient_messages "
            "(channel_id, user_id, username, display_name, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (channel_id, user_id, username, display_name, content, _now_ms()),
        )
        _conn.execute(
            """
            DELETE FROM ambient_messages WHERE channel_id = ? AND id NOT IN (
                SELECT id FROM ambient_messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (channel_id, channel_id, max_messages),
        )


def get_ambient_messages(channel_id, max_messages):
    if max_messages <= 0:
        return []

    rows = _conn.execute(
        "SELECT username, content, display_name, created_at, user_id FROM ambient_messages "
        "WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
        (channel_id, max_messages),
    ).fetchall()
    rows.reverse()
    return [
        {
            "username": r[0] or "",
            "content": r[1],
            "display_name": r[2],
            "created_at": r[3],
            "user_id": r[4],
        }
        for r in rows
    ]


def clear_ambient_messages(channel_id):
    with _conn:
        _conn.execute("DELETE FROM ambient_messages WHERE channel_id = ?", (channel_id,))


def clear_all_ambient_messages():
    with _conn:
        _conn.execute("DELETE FROM ambient_messages")


# --- Preferencia de marcacao ---


def set_no_ping(user_id, no_ping):
    """Pessoa pediu para o bot nao marca-la (ou liberou de novo). Vale em todo canal e
    sobrevive a o!reset: e preferencia da pessoa, nao conversa."""
    with _conn:
        if no_ping:
            _conn.execute(
                "INSERT INTO no_ping (user_id, created_at) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO NOTHING",
                (str(user_id), _now_ms()),
            )
        else:
            _conn.execute("DELETE FROM no_ping WHERE user_id = ?", (str(user_id),))


def get_no_ping():
    return {r[0] for r in _conn.execute("SELECT user_id FROM no_ping")}


# --- Modo silencioso ---


def set_muted(channel_id, muted):
    with _conn:
        if muted:
            _conn.execute(
                "INSERT INTO muted_channels (channel_id, muted_at) VALUES (?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET muted_at = excluded.muted_at",
                (channel_id, _now_ms()),
            )
        else:
            _conn.execute("DELETE FROM muted_channels WHERE channel_id = ?", (channel_id,))


def is_muted(channel_id):
    row = _conn.execute(
        "SELECT 1 FROM muted_channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row is not None
