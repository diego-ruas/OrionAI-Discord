from types import SimpleNamespace as NS

from app.utils.image_processor import image_sources


def media(url):
    return NS(url=url, proxy_url=url + "?proxy")


def test_image_sources_junta_anexo_embed_e_figurinha():
    attachments = [
        NS(url="a", filename="a.png", content_type="image/png", size=1),
        NS(url="b", filename="b.pdf", content_type="application/pdf", size=1),
    ]
    embeds = [
        NS(type="gifv", thumbnail=media("https://t/x.gif"), image=None),
        NS(type="article", thumbnail=media("https://t/capa.png"), image=None),
    ]
    stickers = [
        NS(url="s1", name="oi", format=NS(name="apng")),
        NS(url="s2", name="vet", format=NS(name="lottie")),
    ]
    got = image_sources(attachments, embeds, stickers)
    assert [s.filename for s in got] == ["a.png", "x.gif", "oi.png"]
    assert got[1].url.endswith("?proxy")  # baixa pelo proxy do Discord, nao do terceiro
    assert got[1].content_type is None  # tipo so se sabe ao baixar


def test_embed_sem_proxy_url_e_ignorado():
    # Sem proxy_url so haveria a URL de terceiro: baixar dela pularia a protecao de SSRF.
    embed = NS(type="image", thumbnail=NS(url="http://searxng:8080/x.png", proxy_url=None), image=None)
    assert image_sources([], [embed]) == []
