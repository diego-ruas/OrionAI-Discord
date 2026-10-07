import importlib
import types

import pytest


@pytest.fixture
def perms(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OWNER_IDS", "42, 77")
    importlib.reload(importlib.import_module("app.config"))
    return importlib.reload(importlib.import_module("app.permissions"))


def _membro(user_id):
    # Sem permissoes de moderacao: so o id decide.
    return types.SimpleNamespace(id=user_id, guild_permissions=None, guild=None)


def test_dono_pode_gerenciar_sem_ser_moderador(perms):
    canal = types.SimpleNamespace()
    assert perms.is_owner(_membro(42)) and perms.is_owner(_membro(77))
    assert perms.can_manage(_membro(42), canal)


def test_nao_dono_sem_permissao_nao_gerencia(perms):
    assert not perms.is_owner(_membro(43))
    assert not perms.can_manage(_membro(43), types.SimpleNamespace())
