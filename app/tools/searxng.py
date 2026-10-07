from ..config import config
from ..utils.http_client import get_session
from ..utils.safety import parse_search_results, validate_search_query


async def web_search(query, max_results=5):
    query = validate_search_query(query)
    session = await get_session()
    # safesearch=1: o bot responde num servidor de Discord, nao num buscador aberto.
    async with session.get(
        f"{config.searxng_url}/search",
        params={"q": query, "format": "json", "safesearch": 1},
    ) as res:
        if res.status == 403:
            raise RuntimeError(
                "SearXNG recusou o formato json: habilite `json` em search.formats do settings.yml."
            )
        if not res.ok:
            raise RuntimeError(f"SearXNG respondeu {res.status}.")
        data = await res.json(content_type=None)
    return parse_search_results(data, max_results)
