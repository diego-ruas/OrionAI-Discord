from ..config import config
from ..utils.http_client import get_session
from ..utils.safety import validate_fetch_url, validate_search_query

BASE_URL = "https://api.fastcrw.com/v1"


async def _crw_request(path, body):
    if not config.crw_api_key:
        raise RuntimeError(
            "CRW_API_KEY nao configurada. Crie uma conta gratis em fastcrw.com e "
            "adicione a key no .env."
        )

    session = await get_session()
    async with session.post(
        f"{BASE_URL}{path}",
        json=body,
        headers={"Authorization": f"Bearer {config.crw_api_key}"},
    ) as res:
        if not res.ok:
            text = (await res.text())[:300]
            raise RuntimeError(f"fastCRW respondeu {res.status} em {path}: {text}")
        return await res.json()


async def web_search(query, max_results=5):
    query = validate_search_query(query)
    data = await _crw_request("/search", {"query": query, "limit": max_results})
    results = data.get("results") or data.get("data") or []
    return [
        {
            "title": r.get("title") or (r.get("metadata") or {}).get("title", ""),
            "url": r.get("url") or r.get("link", ""),
        }
        for r in results
    ]


async def fetch_page(url):
    url = validate_fetch_url(url)
    data = await _crw_request("/scrape", {"url": url, "formats": ["markdown"]})
    markdown = data.get("markdown") or (data.get("data") or {}).get("markdown", "")
    if not markdown:
        raise RuntimeError("fastCRW nao retornou conteudo para essa URL.")
    return markdown[:6000]
