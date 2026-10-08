import pytest

from app.utils import burst

K = ("1", 2)


@pytest.fixture(autouse=True)
def limpa():
    burst._pending.clear()
    yield
    burst._pending.clear()


def test_so_a_ultima_e_latest_e_take_junta_tudo():
    for i in (1, 2, 3):
        burst.add(K, i, f"t{i}", False)
    assert [burst.is_latest(K, i) for i in (1, 2, 3)] == [False, False, True]
    assert [e["text"] for e in burst.take(K, 3)] == ["t1", "t2", "t3"]
    assert K not in burst._pending
    assert burst.take(K, 1) == []


def test_imagem_de_outra_mensagem_fica():
    burst.add(K, 1, "a", True)
    burst.add(K, 2, "b", False)
    assert [e["msg_id"] for e in burst.take(K, 2)] == [2]
    assert [e["msg_id"] for e in burst.take(K, 1)] == [1]


def test_discard():
    burst.add(K, 1, "a", False)
    burst.discard(K, 1)
    assert K not in burst._pending
