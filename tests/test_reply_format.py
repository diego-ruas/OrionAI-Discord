from app.utils.reply_format import (
    DISCORD_LIMIT,
    MIN_CHARS_TO_SPLIT,
    TRUNCATION_NOTE,
    split_reply,
    truncate_reply,
    typing_delay,
)


def test_truncate_deixa_texto_curto_intacto():
    assert truncate_reply("  resposta curta  ", 100) == "resposta curta"


def test_truncate_corta_no_fim_de_frase():
    texto = "Primeira frase. " + "x" * 80
    cortado = truncate_reply(texto, 24)
    assert cortado.endswith(TRUNCATION_NOTE)
    assert cortado.startswith("Primeira frase.")
    assert "x" not in cortado


def test_truncate_ignora_ponto_de_corte_cedo_demais():
    # O fim de frase esta antes da metade do limite: respeitar ele jogaria fora quase
    # toda a resposta, entao o corte bruto no limite e preferido.
    texto = "Ok. " + "x" * 80
    cortado = truncate_reply(texto, 40)
    assert cortado.startswith("Ok. xxx")


def test_truncate_sem_ponto_de_corte_limpo_corta_no_limite():
    # Sem espaco nem pontuacao, nao ha quebra melhor que o limite bruto.
    cortado = truncate_reply("y" * 200, 50)
    assert cortado == "y" * 50 + TRUNCATION_NOTE


def test_truncate_aceita_none():
    assert truncate_reply(None, 10) == ""


def test_truncate_fecha_bloco_de_codigo_cortado_no_meio():
    cortado = truncate_reply("```py\n" + "x = 1\n" * 400, 200)
    assert cortado.count("```") % 2 == 0
    assert cortado.endswith(TRUNCATION_NOTE)


def test_split_vazio():
    assert split_reply("") == []
    assert split_reply(None) == []


def test_split_nao_quebra_resposta_curta():
    texto = "Uma linha.\n\nOutra linha."
    assert len(texto) < MIN_CHARS_TO_SPLIT
    assert split_reply(texto) == [texto]


def test_split_quebra_nos_paragrafos():
    paragrafos = ["a" * 100, "b" * 100, "c" * 100]
    assert split_reply("\n\n".join(paragrafos), max_messages=3) == paragrafos


def test_split_respeita_max_messages_juntando_o_resto():
    paragrafos = ["a" * 100, "b" * 100, "c" * 100, "d" * 100]
    partes = split_reply("\n\n".join(paragrafos), max_messages=2)
    assert len(partes) == 2
    assert partes[0] == "a" * 100
    assert partes[1] == "\n\n".join(paragrafos[1:])


def test_split_desabilitado_devolve_texto_inteiro():
    texto = "\n\n".join(["a" * 100, "b" * 100])
    assert split_reply(texto, enabled=False) == [texto]


def test_split_nao_parte_bloco_de_codigo():
    texto = "Segue o codigo:\n\n```python\n" + "print(1)\n" * 30 + "```"
    assert len(texto) > MIN_CHARS_TO_SPLIT
    assert split_reply(texto) == [texto]


def test_split_mantem_rodape_de_corte_junto_do_texto():
    texto = "a" * 100 + "\n\n" + "b" * 100 + TRUNCATION_NOTE
    partes = split_reply(texto, max_messages=3)
    assert partes[-1].endswith(TRUNCATION_NOTE.strip())
    assert partes[-1] != TRUNCATION_NOTE.strip()


def test_split_respeita_limite_tecnico_do_discord():
    partes = split_reply("z" * (DISCORD_LIMIT * 2 + 100), max_messages=1)
    assert len(partes) == 3
    assert all(len(p) <= DISCORD_LIMIT for p in partes)


def test_typing_delay_proporcional_e_limitado():
    assert typing_delay("abcde", chars_per_second=5, max_seconds=10) == 1.0
    assert typing_delay("x" * 1000, chars_per_second=5, max_seconds=3) == 3.0
    assert typing_delay("x", chars_per_second=0, max_seconds=3) == 0.0
