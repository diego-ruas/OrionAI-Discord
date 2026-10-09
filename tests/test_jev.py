import pytest

from app.utils import jev


def noul(name, value):
    return {name: {"type": "noul", "noul": value}}


def choice(name, picked, probs):
    return {name: {"type": "choice", "choice": picked, "confidence": 0.5, "probabilities": probs}}


def data(*parts):
    answers = {}
    for p in parts:
        answers.update(p)
    return {"answers": answers}


def test_parse_noul():
    assert jev.parse_noul(data(noul(jev.Q_FOR_BOT, 0.96)), jev.Q_FOR_BOT) == 0.96


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"answers": {}},
        data({jev.Q_FOR_BOT: {"type": "noul", "noul": "x"}}),
        data(noul(jev.Q_FOR_BOT, 1.5)),
        data(choice(jev.Q_FOR_BOT, "a", {"a": 1})),  # tipo errado
    ],
)
def test_parse_noul_formato_invalido(payload):
    with pytest.raises(ValueError):
        jev.parse_noul(payload, jev.Q_FOR_BOT)


def test_parse_choice_rejeita_opcao_desconhecida():
    bad = data(choice(jev.Q_INTENT, "inventada", {"inventada": 1}))
    with pytest.raises(ValueError):
        jev.parse_choice(bad, jev.Q_INTENT)


def test_build_request_so_com_as_perguntas_pedidas():
    req = jev.build_request("m", {"x": 1}, jev.pick([jev.Q_INTENT]))
    assert req["state"] == {"x": 1}
    assert list(req["questions"]) == [jev.Q_INTENT]


def test_message_questions():
    assert jev.message_questions(0, 0) == []
    assert jev.message_questions(0.6, 0) == [jev.Q_INTENT, jev.Q_LENGTH]
    assert jev.message_questions(0, 0.5) == [jev.Q_INJECTION]


def test_build_state_fatos_do_codigo():
    history = [
        {"role": "user", "user_id": "7", "username": "ana_b", "display_name": "Ana",
         "content": "oi bot", "created_at": 0},
        {"role": "assistant", "content": "e ai", "created_at": 10_000},
        {"role": "user", "user_id": "8", "username": "bob", "display_name": None,
         "content": "kkk", "created_at": 20_000},
    ]
    state = jev.build_state(history, "Ana (@ana_b)", 7, 40_000, "ver https://x.com/a", "UTC")
    assert state["facts"] == {
        "contains_url": True,
        "bot_last_replied_to_same_speaker": True,
        "seconds_since_bot_last_reply": 30,
    }
    assert state["recent_messages"][1]["speaker"] == "bot"
    assert state["recent_messages"][2]["speaker"] == "@bob"
    assert state["new_message"]["speaker_id"] == "7"

    other = jev.build_state(history, "Bob", 8, 40_000, "oi", "UTC")
    assert other["facts"]["bot_last_replied_to_same_speaker"] is False
    assert other["facts"]["contains_url"] is False


def test_build_state_sem_resposta_do_bot():
    state = jev.build_state([], "Ana", 7, 0, "oi", "UTC")
    assert state["facts"]["seconds_since_bot_last_reply"] is None
    assert state["facts"]["bot_last_replied_to_same_speaker"] is False


def answers(intent, p_intent, length, p_length, inj):
    return data(
        choice(jev.Q_INTENT, intent, {intent: p_intent, "other": 1 - p_intent}),
        choice(jev.Q_LENGTH, length, {length: p_length, "medium": 1 - p_length}),
        noul(jev.Q_INJECTION, inj),
    )


def test_interpret_confianca_alta_restringe_ferramentas_e_tamanho():
    got = jev.interpret(answers("search", 0.9, "short", 0.9, 0.9), 0.6, 0.5)
    assert got == {
        "tool_names": ["web_search", "fetch_page"],
        "length_hint": jev.LENGTH_HINTS["short"],
        "injection": True,
    }


def test_interpret_na_duvida_mantem_todas_as_ferramentas():
    got = jev.interpret(answers("search", 0.55, "short", 0.55, 0.1), 0.6, 0.5)
    assert got == {"tool_names": None, "length_hint": "", "injection": False}


def test_interpret_chat_exige_mais_certeza_que_as_outras():
    # 0.7 basta para "search", mas tirar todas as ferramentas pede 0.6 + 0.2.
    assert jev.interpret(answers("search", 0.7, "medium", 0.1, 0), 0.6, 0)["tool_names"]
    assert jev.interpret(answers("chat", 0.7, "medium", 0.1, 0), 0.6, 0)["tool_names"] is None
    assert jev.interpret(answers("chat", 0.85, "medium", 0.1, 0), 0.6, 0)["tool_names"] == []


def test_interpret_other_nunca_restringe():
    assert jev.interpret(answers("other", 0.99, "medium", 0.1, 0), 0.6, 0)["tool_names"] is None


def test_interpret_link_na_mensagem_mantem_leitura_de_pagina():
    got = jev.interpret(answers("chat", 0.95, "medium", 0.1, 0), 0.6, 0, contains_url=True)
    assert got["tool_names"] == ["fetch_page", "web_search"]
    got = jev.interpret(answers("memory", 0.9, "medium", 0.1, 0), 0.6, 0, contains_url=True)
    assert got["tool_names"] == ["forget_fact", "fetch_page", "web_search"]


def test_interpret_desligado_nao_exige_as_respostas():
    assert jev.interpret({}, 0, 0) == {"tool_names": None, "length_hint": "", "injection": False}


FACTS = [{"about": "a", "by": "a", "fact": "x"}, {"about": "b", "by": None, "fact": "y"}]


def test_supported_facts_filtra_pelo_corte():
    got = jev.supported_facts(data(noul("fact_0", 0.9), noul("fact_1", 0.3)), FACTS)
    assert got == [FACTS[0]]


def test_supported_facts_resposta_incompleta_levanta():
    with pytest.raises(ValueError):
        jev.supported_facts(data(noul("fact_0", 0.9)), FACTS)


def test_fact_check_state():
    rows = [{"role": "assistant", "content": "oi"}]
    state = jev.fact_check_state(rows, FACTS)
    assert state["messages"][0]["speaker"] == "bot"
    assert [c["id"] for c in state["candidate_facts"]] == ["fact_0", "fact_1"]
    assert state["candidate_facts"][1]["by"] == ""
