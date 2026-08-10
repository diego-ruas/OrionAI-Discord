"""Presenca do bot: aquele "Jogando/Assistindo/Ouvindo ..." embaixo do nome.

Bot nao faz Rich Presence de verdade - o Discord aceita de bots apenas o tipo, o nome
e (no status personalizado) o state; imagem, botao e party sao ignorados. O que da para
fazer bem e alternar frases curtas alimentadas por dados reais do bot.

A configuracao vem de PRESENCE, uma lista separada por "|" no formato "tipo:texto":

    listening:{prefix}ajuda|watching:{guilds} servidores

Marcadores disponiveis: {prefix}, {guilds}, {model}. Uma entrada cujo numero der zero
e pulada, para o bot nao ficar anunciando "0 servidores".
"""

import re

import discord

# Limite do Discord para o nome da atividade.
MAX_ACTIVITY_NAME = 128

ACTIVITY_TYPES = {
    "playing": discord.ActivityType.playing,
    "jogando": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "assistindo": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "ouvindo": discord.ActivityType.listening,
    "competing": discord.ActivityType.competing,
    "competindo": discord.ActivityType.competing,
    "custom": discord.ActivityType.custom,
}

STATUS_TYPES = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "ausente": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "ocupado": discord.Status.dnd,
    "invisible": discord.Status.invisible,
    "invisivel": discord.Status.invisible,
}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def parse_status(name):
    return STATUS_TYPES.get((name or "").strip().lower(), discord.Status.online)


def parse_spec(spec):
    """Transforma a string de PRESENCE numa lista de (ActivityType, template).

    Entradas invalidas sao descartadas com aviso, em vez de derrubar o bot no boot por
    causa de uma virgula fora do lugar numa variavel de ambiente.
    """
    entries = []
    for raw in (spec or "").split("|"):
        raw = raw.strip()
        if not raw:
            continue

        kind, sep, text = raw.partition(":")
        if not sep or not text.strip():
            print(f"[presenca] Entrada ignorada (formato 'tipo:texto'): {raw!r}")
            continue

        activity_type = ACTIVITY_TYPES.get(kind.strip().lower())
        if activity_type is None:
            opcoes = ", ".join(sorted(set(ACTIVITY_TYPES)))
            print(f"[presenca] Tipo desconhecido {kind!r} em {raw!r}. Use: {opcoes}")
            continue

        entries.append((activity_type, text.strip()))

    return entries


def render(template, stats):
    """Preenche os marcadores. Devolve None se algum numero for zero."""
    for name in _PLACEHOLDER.findall(template):
        if name not in stats:
            print(f"[presenca] Marcador desconhecido: {{{name}}}")
            return None
        value = stats[name]
        # "0 servidores" e pior do que nao mostrar nada.
        if isinstance(value, int) and value == 0:
            return None

    return _PLACEHOLDER.sub(lambda m: str(stats[m.group(1)]), template)[:MAX_ACTIVITY_NAME]


def build_activity(activity_type, text):
    if activity_type is discord.ActivityType.custom:
        # No status personalizado o Discord mostra o campo state, nao o name.
        return discord.CustomActivity(name=text, state=text)
    return discord.Activity(type=activity_type, name=text)


def build_rotation(entries, stats):
    """Lista de atividades prontas para exibir, ja sem as que nao se aplicam agora."""
    activities = []
    for activity_type, template in entries:
        text = render(template, stats)
        if text:
            activities.append(build_activity(activity_type, text))
    return activities
