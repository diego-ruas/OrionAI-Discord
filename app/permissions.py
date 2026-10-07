"""Quem pode apagar ou alterar dados do bot.

So operacoes destrutivas passam por aqui: limpar historico e apagar memoria de longo
prazo. Ler (memoria, status) e conversar continuam livres para todo mundo - o objetivo e evitar estrago, nao burocratizar o uso.

Em DM nao existe hierarquia e o dado e da propria pessoa, entao la e sempre permitido:
o contrario trancaria alguem para fora do proprio historico.
"""

import discord

from .config import config


def _has_admin_role(member):
    """Cargo listado em ADMIN_ROLES, aceito por nome ou por id."""
    if not config.admin_roles:
        return False

    roles = getattr(member, "roles", None) or []
    names = {getattr(r, "name", "").strip().lower() for r in roles}
    ids = {str(getattr(r, "id", "")) for r in roles}
    return any(entry in names or entry in ids for entry in config.admin_roles)


def can_manage(author, channel):
    """True se a pessoa pode apagar/alterar dados do bot neste canal."""
    if isinstance(channel, discord.DMChannel):
        return True

    # Permissao no canal, nao so no servidor: os dados do bot sao por canal, entao um
    # overwrite de canal concedendo ou negando gerenciar mensagens tem que valer.
    if isinstance(author, discord.Member) and hasattr(channel, "permissions_for"):
        perms = channel.permissions_for(author)
    else:
        perms = getattr(author, "guild_permissions", None)
    if perms is not None:
        # administrator cobre tudo; manage_guild e manage_messages sao o que
        # normalmente distingue moderacao de membro comum.
        if perms.administrator or perms.manage_guild or perms.manage_messages:
            return True

    guild = getattr(author, "guild", None)
    if guild is not None and getattr(guild, "owner_id", None) == getattr(author, "id", None):
        return True

    return _has_admin_role(author)


def denial_message():
    extra = ""
    if config.admin_roles:
        cargos = ", ".join(config.admin_roles)
        extra = f" Tambem vale para quem tem um destes cargos: {cargos}."
    return (
        "Isso apaga dados do canal, entao so quem modera pode fazer - precisa de "
        "permissao de administrador, gerenciar servidor ou gerenciar mensagens." + extra
    )
