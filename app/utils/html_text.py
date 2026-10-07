from html.parser import HTMLParser

# trafilatura extrai so o conteudo principal (sem menu, rodape, anuncio) e devolve
# markdown. E opcional: sem ela cai no extrator simples abaixo, que funciona mas traz
# mais ruido da pagina.
try:
    import trafilatura

    TRAFILATURA_AVAILABLE = True
except ImportError:  # pragma: no cover - ambiente sem trafilatura
    trafilatura = None
    TRAFILATURA_AVAILABLE = False

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer", "form"}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "table", "pre", "blockquote",
}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _fallback_extract(html):
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def extract_text(html):
    """Texto legivel de uma pagina HTML, ou string vazia se nao houver."""
    text = ""
    if TRAFILATURA_AVAILABLE:
        try:
            text = trafilatura.extract(
                html,
                output_format="markdown",
                include_comments=False,
                include_links=False,
                favor_recall=True,
            ) or ""
        except Exception as err:  # noqa: BLE001 - HTML torto nao pode derrubar a tool
            print(f"[web] trafilatura falhou ({type(err).__name__}); usando extrator simples.")
    if not text.strip():
        text = _fallback_extract(html)
    return text.strip()
