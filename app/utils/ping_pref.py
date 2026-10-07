"""Pedido da propria pessoa para o bot nao marca-la (ou voltar a marcar).

Regra de prompt sozinha nao segura: o modelo esquece e marca de novo na mensagem seguinte.
Aqui o pedido e detectado no texto da pessoa e guardado no banco; o codigo e quem corta o
ping depois (ver resolve_mentions). So vale para "me": pedir para nao marcar outra pessoa
nao muda a preferencia dela.
"""

import re
import unicodedata

_VERB = r"(ping\w*|marc\w*|marq\w*|mencion\w*)"
_STOP = re.compile(
    rf"\b(nao|nunca|jamais)\s+(pode(m)?\s+)?me\s+{_VERB}\b"
    rf"|\b(par[ae]r?|chega|cansei)\s+de\s+me\s+{_VERB}\b"
)
_ALLOW = re.compile(rf"\bpode(m)?\s+(sim\s+)?(voltar\s+a\s+)?me\s+{_VERB}\b")


def _fold(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def detect(text):
    """"stop" se pediu para nao ser marcada, "allow" se liberou de novo, None caso contrario."""
    folded = _fold(text or "")
    if _STOP.search(folded):
        return "stop"
    if _ALLOW.search(folded):
        return "allow"
    return None


def asks_to_mention(text):
    """O texto pede para o bot marcar/chamar alguem (inclusive o proprio autor)?"""
    return re.search(r"\b(marc\w*|ping\w*|chama\w*|mencion\w*)\b", _fold(text or "")) is not None
