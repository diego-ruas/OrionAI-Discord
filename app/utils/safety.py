import ipaddress
import re
import time
from urllib.parse import urlparse

MAX_URL_CHARS = 500
MAX_QUERY_CHARS = 300

# Menções de usuario no formato do Discord (<@id> ou <@!id>).
_USER_MENTION = re.compile(r"<@!?(\d+)>")


def validate_fetch_url(url):
    """Valida a URL pedida ao fetch_page; levanta ValueError se nao for segura.

    A requisicao sai do fastCRW, nao do host do bot, entao o risco aqui nao e SSRF e sim
    exfiltracao: um modelo induzido por injecao pode embutir dados do contexto na URL de
    um servidor do atacante. Por isso a URL e curta, so http(s) e sem IP/localhost.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL vazia.")
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise ValueError("URL longa demais.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("So URLs http/https sao aceitas.")
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("Host nao permitido.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("URL com IP literal nao e permitida.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Porta nao permitida.")
    if parsed.username or parsed.password:
        raise ValueError("URL com credenciais nao e permitida.")
    return url


def validate_search_query(query):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Consulta vazia.")
    return query.strip()[:MAX_QUERY_CHARS]


def escape_like(text):
    """Escapa curingas do LIKE (use com ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def limit_user_mentions(text, max_mentions):
    """Mantem so as primeiras `max_mentions` mencoes de usuario; o resto vira texto
    puro, para o bot nao virar ferramenta de ping em massa."""
    count = 0

    def repl(match):
        nonlocal count
        count += 1
        return match.group(0) if count <= max_mentions else "alguem"

    return _USER_MENTION.sub(repl, text)


class RateLimiter:
    """Janela deslizante por chave. check() devolve "ok", "warn" (primeiro excesso da
    janela, hora de avisar) ou "drop" (ignorar em silencio)."""

    def __init__(self, limit, window_seconds, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits = {}
        self._warned = {}

    def check(self, key):
        if self.limit <= 0:
            return "ok"
        now = self.clock()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(hits) < self.limit:
            hits.append(now)
            self._hits[key] = hits
            self._warned.pop(key, None)
            return "ok"
        self._hits[key] = hits
        if self._warned.get(key, -self.window) <= now - self.window:
            self._warned[key] = now
            return "warn"
        return "drop"

    def prune(self):
        """Remove chaves paradas, para o dicionario nao crescer sem limite."""
        now = self.clock()
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            self._hits.pop(key, None)
            self._warned.pop(key, None)
