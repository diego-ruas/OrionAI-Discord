import pytest

from app.utils import ping_pref
from app.utils.chat_format import known_people, resolve_mentions, strip_leading_mention


@pytest.mark.parametrize(
    "text",
    [
        "Mandei não me pingar",
        "não me marca mais",
        "nao me marque",
        "para de me marcar",
        "PARA DE ME PINGAR PORRA",
        "cansei de me mencionar",
    ],
)
def test_stop(text):
    assert ping_pref.detect(text) == "stop"


@pytest.mark.parametrize("text", ["pode me marcar de novo", "pode sim me pingar", "podem me marcar"])
def test_allow(text):
    assert ping_pref.detect(text) == "allow"


@pytest.mark.parametrize(
    "text",
    ["marca o niro", "não marca o niro", "quem me marcou?", "oi bot", "não pode me marcar mais"],
)
def test_nao_dispara(text):
    # "nao pode me marcar" e stop, os demais nao mexem na preferencia de quem escreveu
    expected = "stop" if text == "não pode me marcar mais" else None
    assert ping_pref.detect(text) == expected


def test_asks_to_mention():
    assert ping_pref.asks_to_mention("marca o niro")
    assert not ping_pref.asks_to_mention("kkk como assim")


def test_no_ping_corta_ping_mas_mantem_nome():
    people = known_people([{"user_id": "1", "username": "niro_x", "display_name": "Niro"}])
    assert resolve_mentions("oi @Niro", people, no_ping={"1"}) == "oi @Niro"
    assert resolve_mentions("oi <@1>", people, no_ping={"1"}) == "oi @Niro"
    assert resolve_mentions("oi @Niro", people) == "oi <@1>"


def test_strip_leading_mention():
    assert strip_leading_mention("<@1>\n\nkkk", 1) == "kkk"
    assert strip_leading_mention("kkk <@1> oi", 1) == "kkk <@1> oi"
    assert strip_leading_mention("<@2> oi", 1) == "<@2> oi"


def test_sem_pedido_de_marcar_nada_vira_ping():
    people = known_people(
        [{"user_id": "1", "username": "SPÆRX", "display_name": "SPÆRX"},
         {"user_id": "2", "username": "niro_x", "display_name": "Niro"}]
    )
    out = resolve_mentions("SPÆRX (@SPÆRX) e @Niro (@niro_x) kkk <@1>", people, allow_ping=False)
    assert "<@" not in out and "@" not in out
    assert out == "SPÆRX e Niro kkk SPÆRX"


def test_rotulo_copiado_do_prompt_volta_a_ser_so_o_apelido():
    people = known_people([{"user_id": "2", "username": "niro_x", "display_name": "Niro"}])
    assert resolve_mentions("oi Niro (@niro_x)!", people, allow_ping=False) == "oi Niro!"
    # mesmo com ping liberado, o rotulo copiado nao vira marcacao
    assert resolve_mentions("oi Niro (@niro_x)!", people) == "oi Niro!"


def test_blocked_names_in():
    from app.utils.chat_format import blocked_names_in

    people = known_people(
        [{"user_id": "1", "username": "niro_x", "display_name": "Niro"},
         {"user_id": "2", "username": "pendy", "display_name": "Pendy"}]
    )
    assert blocked_names_in("Marca o niro", people, {"1"}) == ["Niro"]
    assert blocked_names_in("marca o pendy", people, {"1"}) == []
    assert blocked_names_in("niroxyz", people, {"1"}) == []
