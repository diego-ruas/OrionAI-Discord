from app.utils.links import extract_urls


def test_extract_urls():
    text = "olha https://a.com/x), e <https://b.com/y?q=1>. de novo https://a.com/x https://c.com/f.png https://d.com"
    assert extract_urls(text) == ["https://a.com/x", "https://b.com/y?q=1"]
    assert extract_urls(text, limit=3, skip={"https://a.com/x"}) == ["https://b.com/y?q=1", "https://d.com"]
    assert extract_urls(None) == []
