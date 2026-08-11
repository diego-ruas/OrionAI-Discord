"""Sessao HTTP compartilhada para reuso de conexoes TCP/TLS (Keep-Alive).

Evita o custo de abrir e fechar conexao TLS a cada chamada do OpenRouter,
busca do fastCRW ou download de imagem no Discord.
"""

import aiohttp

_session = None


async def get_session():
    """Retorna uma ClientSession compartilhada, criando uma se necessario."""
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=60)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session


async def close_session():
    """Encerra a sessao de forma limpa ao desligar o bot."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
