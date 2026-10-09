import re

_URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
# Imagem e video nao tem texto para ler: imagem vai para a visao, o resto nao e lido.
_MEDIA = re.compile(r"\.(png|jpe?g|gif|webp|mp4|webm|mov)$", re.IGNORECASE)


def extract_urls(text, limit=2, skip=()):
    """Links da mensagem que valem ser lidos, na ordem, sem repetir. `skip` sao URLs ja
    tratadas de outro jeito (GIF/imagem que o Discord transformou em embed)."""
    urls = []
    for match in _URL.finditer(text or ""):
        url = match.group(0).rstrip(".,;:!?)]}'\"")
        path = url.split("?")[0].split("#")[0]
        if _MEDIA.search(path) or url in skip or url in urls:
            continue
        urls.append(url)
    return urls[:limit]
