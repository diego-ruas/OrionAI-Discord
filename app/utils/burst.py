"""Junta mensagens seguidas da mesma pessoa no mesmo canal numa resposta so. Estado em
memoria, chaves (channel_id_str, user_id_int); cada entrada guarda id, texto e se tem
imagem."""

_pending = {}


def add(key, msg_id, text, has_images):
    _pending.setdefault(key, []).append(
        {"msg_id": msg_id, "text": text, "has_images": has_images}
    )


def is_latest(key, msg_id):
    entries = _pending.get(key)
    return bool(entries) and entries[-1]["msg_id"] == msg_id


def take(key, own_id):
    """Tira e devolve, na ordem, as mensagens pendentes sem imagem mais a propria. Se a
    propria ja foi absorvida por outra resposta, devolve [] e nao mexe em nada. Mensagem
    de outra com imagem fica: quem a processa e a propria mensagem dela."""
    entries = _pending.get(key, [])
    if not any(e["msg_id"] == own_id for e in entries):
        return []
    taken = [e for e in entries if e["msg_id"] == own_id or not e["has_images"]]
    rest = [e for e in entries if e not in taken]
    if rest:
        _pending[key] = rest
    else:
        _pending.pop(key, None)
    return taken


def discard(key, msg_id):
    entries = [e for e in _pending.get(key, []) if e["msg_id"] != msg_id]
    if entries:
        _pending[key] = entries
    else:
        _pending.pop(key, None)
