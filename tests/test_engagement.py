import pytest

from app.utils import engagement


@pytest.fixture(autouse=True)
def limpo():
    engagement._last_engagement.clear()
    engagement._stopped_at.clear()
    yield
    engagement._last_engagement.clear()
    engagement._stopped_at.clear()


def test_janela_expira():
    engagement.mark("c", 1, 15, now=0)
    assert engagement.in_window("c", 1, 15, now=10)
    assert not engagement.in_window("c", 1, 15, now=16)


def test_outra_pessoa_falando_encerra_janela():
    engagement.mark("c", 1, 15, now=0)
    engagement.note_message("c", 1)  # a propria pessoa
    assert engagement.in_window("c", 1, 15, now=10)
    engagement.note_message("d", 2)  # outro canal
    assert engagement.in_window("c", 1, 15, now=10)
    engagement.note_message("c", 2)
    assert not engagement.in_window("c", 1, 15, now=10)


def test_clear_fecha_janela_e_registra_parada():
    engagement.mark("c", 1, 15, now=0)
    engagement.clear("c", 1, now=5)
    assert not engagement.in_window("c", 1, 15, now=6)
    assert engagement.stopped_after("c", 1, 4)
    assert not engagement.stopped_after("c", 1, 6)
