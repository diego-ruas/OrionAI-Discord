import ipaddress
import re
import unicodedata
import time
from urllib.parse import urlparse

MAX_URL_CHARS = 500
MAX_QUERY_CHARS = 300

# Menções de usuario no formato do Discord (<@id> ou <@!id>).
_USER_MENTION = re.compile(r"<@!?(\d+)>")


def validate_fetch_url(url):
    """Valida a URL pedida ao fetch_page; levanta ValueError se nao for segura.

    Com a busca local (SEARXNG_URL) a requisicao sai do host do bot, entao aqui tambem e
    barreira de SSRF (o resto esta em app/tools/webfetch.py). Em qualquer caso ha o
    risco de exfiltracao: um modelo induzido por injecao pode embutir dados do contexto
    na URL de um servidor do atacante. Por isso a URL e curta, so http(s) e sem
    IP/localhost.
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


def is_public_ip(address):
    """True so para enderecos roteaveis na internet. Bloqueia loopback, rede privada,
    link-local (inclui o endpoint de metadados 169.254.169.254), CGNAT e multicast.
    IPv6 mapeado de IPv4 (::ffff:10.0.0.1) e avaliado pelo IPv4 embutido."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def parse_search_results(data, max_results):
    """Reduz a resposta JSON do SearXNG a titulo, url e um trecho curto."""
    results = []
    for r in data.get("results") or []:
        if not isinstance(r, dict) or not r.get("url"):
            continue
        results.append(
            {
                "title": str(r.get("title") or "")[:200],
                "url": str(r["url"]),
                "snippet": " ".join(str(r.get("content") or "").split())[:250],
            }
        )
        if len(results) >= max_results:
            break
    return results


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


def _fold(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


def prompt_fragments(prompt):
    """Pedacos longos do prompt de sistema, normalizados, para detectar copia na resposta."""
    pieces = re.split(r"[.;:\n]+", _fold(prompt))
    return frozenset(p.strip() for p in pieces if len(p.strip()) >= 40)


def leaks_prompt(reply, fragments):
    """Um pedaco sozinho pode ser coincidencia; dois ou mais e copia do prompt."""
    folded = _fold(reply)
    return sum(1 for f in fragments if f in folded) >= 2


_INJECTION = [
    re.compile(p)
    for p in (
        r"ignor\w* (todas |as |suas |tuas |de )*(instruc|regra|orden)",
        r"(mostr|revel|repit|imprim)\w* (o |a |seu |sua |teu |tua )*(prompt|instruc)",
        r"system prompt|prompt de sistema|jailbreak",
        r"modo (dev|desenvolvedor|deus|sem filtro|sem restric)",
        r"\bdan\b",
        r"sem (filtro|regra|restric)",
        r"a partir de agora (voce|vc|tu) (e|sera|vai ser)",
        r"finja (ser|que)",
    )
]


def looks_like_injection(text):
    folded = _fold(text)
    return any(p.search(folded) for p in _INJECTION)


_THIRD_PARTY_ORDER = re.compile(
    r"\b(toda|todas|cada|sempre)\b.{0,50}\b(mensage\w*|respost\w*|vez|fala\w*)\b"
    r".{0,60}\b(respond\w*|termin\w*|comec\w*|fal\w*|cham\w*|us\w*|dig\w*)"
)


def orders_other_user(text):
    """Ordem de comportamento fixo dirigida a outra pessoa ("toda mensagem do @fulano
    termine com X"). So conta se a mensagem cita alguem com @."""
    if "@" not in str(text or ""):
        return False
    return bool(_THIRD_PARTY_ORDER.search(_fold(text)))


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
