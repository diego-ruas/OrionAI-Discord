"""Janela de follow-up: por alguns segundos depois de responder alguem, o bot responde
as mensagens dessa pessoa sem precisar de mencao. Estado em memoria, chaves
(channel_id_str, user_id_int)."""

import time

# Ultima vez que o bot respondeu cada pessoa em cada canal.
_last_engagement = {}

# Quando cada pessoa mandou `parar` por ultimo: uma resposta que ja estava em andamento
# nao pode reabrir a janela de follow-up que a pessoa acabou de fechar.
_stopped_at = {}


def mark(channel_id, user_id, window_seconds, now=None):
    now = time.monotonic() if now is None else now
    # Limpa marcacoes expiradas de vez em quando, pra tabela nao crescer sem limite.
    if len(_last_engagement) > 500:
        for key, when in list(_last_engagement.items()):
            if (now - when) > window_seconds:
                del _last_engagement[key]
    _last_engagement[(channel_id, user_id)] = now


def clear(channel_id, user_id, now=None):
    """Encerra a janela de follow-up na hora (comando `parar`)."""
    now = time.monotonic() if now is None else now
    if len(_stopped_at) > 500:
        for key, when in list(_stopped_at.items()):
            if (now - when) > 600:
                del _stopped_at[key]
    _stopped_at[(channel_id, user_id)] = now
    _last_engagement.pop((channel_id, user_id), None)


def stopped_after(channel_id, user_id, started):
    return _stopped_at.get((channel_id, user_id), -1.0) >= started


def in_window(channel_id, user_id, window_seconds, now=None):
    if window_seconds <= 0:
        return False
    now = time.monotonic() if now is None else now
    last = _last_engagement.get((channel_id, user_id))
    return last is not None and (now - last) <= window_seconds


def note_message(channel_id, author_id):
    """Outra pessoa falou no canal: encerra a janela de follow-up de todo mundo menos
    dela. Em canal cheio, quem recebeu resposta pode estar falando com outra pessoa."""
    for key in [k for k in _last_engagement if k[0] == channel_id and k[1] != author_id]:
        del _last_engagement[key]
