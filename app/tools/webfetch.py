import asyncio
from urllib.parse import urljoin

from ..utils.html_text import extract_text
from ..utils.http_client import get_public_session
from ..utils.safety import validate_fetch_url

MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_CHARS = 6000
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/markdown")
USER_AGENT = "Mozilla/5.0 (compatible; OrionAI-Discord/1.0)"


async def _read_limited(res):
    # Teto de bytes lido em streaming: pagina gigante nao pode encher a memoria.
    chunks, total = [], 0
    async for chunk in res.content.iter_chunked(65536):
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_BODY_BYTES:
            break
    return b"".join(chunks)[:MAX_BODY_BYTES]


def _decode(data, charset):
    try:
        return data.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


async def fetch_page(url):
    """Baixa a pagina a partir do proprio host e devolve o texto principal.

    Redirecionamento e seguido a mao: cada destino passa por validate_fetch_url (que
    recusa IP literal) e a conexao passa pelo resolvedor que recusa IP nao publico. So
    o aiohttp seguindo sozinho deixaria um 302 para http://192.168.0.1/ passar."""
    url = validate_fetch_url(url)
    session = await get_public_session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}

    for _ in range(MAX_REDIRECTS + 1):
        async with session.get(url, headers=headers, allow_redirects=False) as res:
            if res.status in (301, 302, 303, 307, 308):
                location = res.headers.get("Location")
                if not location:
                    raise RuntimeError("Redirecionamento sem destino.")
                url = validate_fetch_url(urljoin(url, location))
                continue
            if res.status >= 400:
                raise RuntimeError(f"A pagina respondeu HTTP {res.status}.")
            content_type = (res.content_type or "").lower()
            if content_type not in TEXT_TYPES:
                raise RuntimeError(f"Tipo de conteudo nao suportado: {content_type or 'desconhecido'}.")
            body = await _read_limited(res)
            text = _decode(body, res.charset)
            break
    else:
        raise RuntimeError("Redirecionamentos demais.")

    if content_type == "text/html" or content_type == "application/xhtml+xml":
        # Parsing de HTML e CPU: fora do event loop.
        text = await asyncio.to_thread(extract_text, text)
    text = text.strip()
    if not text:
        raise RuntimeError("Nao consegui extrair texto dessa pagina.")
    return text[:MAX_CHARS]
