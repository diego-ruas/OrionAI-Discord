"""Garante que o prompt de sistema sempre carrega os blocos obrigatorios.

O SYSTEM_PROMPT e customizavel por env var; os blocos de tom, raciocinio, memoria e
seguranca nao sao - eles sao anexados por cima justamente para nao poderem ser
desligados de fora. Se alguem remover um deles de build_system_prompt sem querer, o
bot continua subindo normalmente e a regressao passa despercebida.
"""

import importlib

import pytest


@pytest.fixture
def config_module(monkeypatch):
    # Config e instanciado na importacao e exige as chaves obrigatorias.
    monkeypatch.setenv("DISCORD_TOKEN", "token-de-teste")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    monkeypatch.delenv("SYSTEM_PROMPT", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    return importlib.reload(importlib.import_module("app.config"))


def test_faltando_variavel_obrigatoria_falha_cedo(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    # load_dotenv nao pode ressuscitar a variavel a partir de um .env local do dev.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        importlib.reload(importlib.import_module("app.config"))


def test_blocos_obrigatorios_sempre_presentes(config_module):
    prompt = config_module.config.build_system_prompt()
    for bloco in (
        config_module.NATURALNESS_INSTRUCTIONS,
        config_module.REASONING_INSTRUCTIONS,
        config_module.PLAYFUL_INSTRUCTIONS,
        config_module.MENTION_INSTRUCTIONS,
        config_module.MEMORY_INSTRUCTIONS,
        config_module.NO_SCHEDULING_INSTRUCTIONS,
        config_module.SAFETY_INSTRUCTIONS,
    ):
        assert bloco in prompt


def test_persona_customizada_nao_desliga_as_regras(config_module, monkeypatch):
    monkeypatch.setenv("SYSTEM_PROMPT", "Voce e um pirata e so fala em versos.")
    recarregado = importlib.reload(config_module)
    prompt = recarregado.config.build_system_prompt()
    assert "pirata" in prompt
    assert recarregado.PLAYFUL_INSTRUCTIONS in prompt
    assert recarregado.SAFETY_INSTRUCTIONS in prompt
    # O bloco de tom vem depois da persona: em conflito, o ultimo bloco e o que vale.
    assert prompt.index("pirata") < prompt.index(recarregado.PLAYFUL_INSTRUCTIONS)


def test_contexto_dinamico_vai_no_fim(config_module):
    prompt = config_module.config.build_system_prompt("Contexto de agora: terca-feira.")
    assert prompt.endswith("Contexto de agora: terca-feira.")
    assert config_module.SAFETY_INSTRUCTIONS in prompt


def test_fallbacks_padrao_existem_e_sao_free(config_module):
    fallbacks = config_module.config.fallback_models
    assert fallbacks, "sem fallback, um 429 do modelo principal vira falha de resposta"
    assert all(m.endswith(":free") for m in fallbacks)
    assert config_module.config.model not in fallbacks


def _recarregar(monkeypatch, **env):
    for nome, valor in env.items():
        monkeypatch.setenv(nome, valor)
    return importlib.reload(importlib.import_module("app.config"))


def test_numero_vazio_cai_no_default(config_module, monkeypatch):
    recarregado = _recarregar(monkeypatch, VISION_MAX_IMAGE_PX="")
    assert recarregado.config.vision_max_image_px == 1024


def test_numero_invalido_aponta_a_variavel(config_module, monkeypatch):
    with pytest.raises(RuntimeError, match="VISION_MAX_IMAGE_PX"):
        _recarregar(monkeypatch, VISION_MAX_IMAGE_PX="abc")


def test_fallback_vazio_usa_lista_padrao(config_module, monkeypatch):
    recarregado = _recarregar(monkeypatch, OPENROUTER_FALLBACK_MODELS="")
    assert recarregado.config.fallback_models
    assert all(m.endswith(":free") for m in recarregado.config.fallback_models)


def test_cadeia_so_inclui_google_com_chave(config_module, monkeypatch):
    from app import openrouter

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    sem = importlib.reload(importlib.import_module("app.config"))
    importlib.reload(openrouter)
    assert all(ep is None for _, ep in openrouter.default_chain())

    monkeypatch.setenv("GOOGLE_API_KEY", "chave-google")
    monkeypatch.setenv("GOOGLE_MODELS", "gemini-a,gemini-b")
    importlib.reload(importlib.import_module("app.config"))
    importlib.reload(openrouter)
    chain = openrouter.default_chain()
    assert [m for m, _ in chain[-2:]] == ["gemini-a", "gemini-b"]
    assert chain[-1][1] == (openrouter.GOOGLE_API_URL, "chave-google")
    # principal e fallbacks do OpenRouter vem antes e usam o endpoint padrao
    assert chain[0] == (sem.config.model, None)
    assert all(ep is None for _, ep in chain[:-2])
