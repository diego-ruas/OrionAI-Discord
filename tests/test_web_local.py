import asyncio

import pytest

from app.utils.safety import parse_search_results as parse_results
from app.utils import html_text
from app.utils.http_client import PublicOnlyResolver
from app.utils.safety import is_public_ip


@pytest.mark.parametrize(
    "ip,expected",
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("192.168.1.10", False),
        ("172.16.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("::ffff:10.0.0.1", False),
        ("224.0.0.1", False),
        ("nao-e-ip", False),
    ],
)
def test_is_public_ip(ip, expected):
    assert is_public_ip(ip) is expected


def test_resolver_bloqueia_host_que_resolve_para_loopback():
    with pytest.raises(OSError):
        asyncio.run(PublicOnlyResolver().resolve("localhost", 80))


HTML = """<html><head><title>t</title><style>.x{}</style></head><body>
<nav>menu lixo</nav><article><h1>Titulo</h1><p>Primeiro paragrafo com bastante texto
util para o extrator reconhecer como conteudo principal da pagina.</p>
<p>Segundo paragrafo, tambem com texto suficiente para contar como conteudo.</p></article>
<script>var x = "script lixo";</script><footer>rodape lixo</footer></body></html>"""


def test_extract_text_remove_script_e_pega_conteudo():
    text = html_text.extract_text(HTML)
    assert "Primeiro paragrafo" in text
    assert "script lixo" not in text


def test_fallback_sem_trafilatura(monkeypatch):
    monkeypatch.setattr(html_text, "TRAFILATURA_AVAILABLE", False)
    text = html_text.extract_text(HTML)
    assert "Primeiro paragrafo" in text and "Segundo paragrafo" in text
    assert "script lixo" not in text and "menu lixo" not in text and "rodape lixo" not in text


def test_parse_results():
    data = {
        "results": [
            {"title": "A", "url": "https://a.com", "content": "  um\n\ntrecho "},
            {"title": "sem url"},
            "lixo",
            {"title": "B", "url": "https://b.com"},
            {"title": "C", "url": "https://c.com"},
        ]
    }
    got = parse_results(data, 2)
    assert got == [
        {"title": "A", "url": "https://a.com", "snippet": "um trecho"},
        {"title": "B", "url": "https://b.com", "snippet": ""},
    ]
    assert parse_results({}, 5) == []
