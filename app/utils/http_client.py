"""Sessao HTTP compartilhada para reuso de conexoes TCP/TLS (Keep-Alive).

Evita o custo de abrir e fechar conexao TLS a cada chamada do OpenRouter,
busca do fastCRW ou download de imagem no Discord.
"""

import asyncio
import socket

import aiohttp
from aiohttp.abc import AbstractResolver

from .safety import is_public_ip

_session = None
_public_session = None


class PublicOnlyResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        result = []
        for fam, _, _, _, addr in infos:
            # Basta um endereco nao publico para recusar: evita o truque de um dominio
            # que devolve um IP publico e outro interno.
            if not is_public_ip(addr[0]):
                raise OSError(f"Endereco nao publico bloqueado para {host}")
            result.append(
                {"hostname": host, "host": addr[0], "port": port, "family": fam, "proto": 0, "flags": 0}
            )
        return result

    async def close(self):
        pass


async def get_session():
    """Retorna uma ClientSession compartilhada, criando uma se necessario."""
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=60)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session


async def get_public_session():
    """Sessao so para buscar paginas da internet a pedido do modelo.

    O resolvedor recusa qualquer host que resolva para IP nao publico (rede local do
    NAS, loopback, metadados): sem isso o bot viraria um proxy para a rede interna.
    Sessao propria, sem cookies compartilhados e sem proxy do ambiente."""
    global _public_session
    if _public_session is None or _public_session.closed:
        connector = aiohttp.TCPConnector(
            resolver=PublicOnlyResolver(), use_dns_cache=False, limit=10
        )
        _public_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=20),
            trust_env=False,
        )
    return _public_session


async def close_session():
    """Encerra as sessoes de forma limpa ao desligar o bot."""
    global _session, _public_session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
    if _public_session is not None and not _public_session.closed:
        await _public_session.close()
        _public_session = None
