"""Le pedidos de lembrete direto do texto, sem depender do modelo.

Modelo gratuito as vezes responde "pode deixar" sem chamar a ferramenta, e a pessoa
fica esperando um aviso que nunca vem. Interpretar "daqui 1 minuto" e "amanha as 9" e
trabalho deterministico - nao precisa de IA e nao pode falhar por sorte.

Isto e uma rede de seguranca: so entra em acao quando o modelo NAO agendou nada. Se
ele chamar a ferramenta corretamente, nada aqui roda.
"""

import re
import unicodedata
from datetime import datetime, timedelta

from .clock import _resolve_zone

# Verbos que caracterizam um pedido de lembrete.
_GATILHO = re.compile(
    r"\b(me\s+)?(lembr[ae]|lembre|avis[ae]|avise|acorde|acorda)\b", re.IGNORECASE
)

# "daqui 1 minuto", "daqui a 20 min", "em 2 horas", "daqui a 3 dias"
_RELATIVO = re.compile(
    r"\b(?:daqui\s+(?:a\s+)?|em\s+|dentro\s+de\s+)(\d{1,4})\s*"
    r"(minutos?|mins?|m|horas?|hrs?|h|dias?|semanas?)\b",
    re.IGNORECASE,
)

# "amanha as 9", "hoje as 15:30", "as 8h", "as 20:00"
_ABSOLUTO = re.compile(
    r"\b(amanha|hoje|depois\s+de\s+amanha)?\s*(?:as|à?s)\s+(\d{1,2})(?:[:h](\d{2}))?\b",
    re.IGNORECASE,
)

_UNIDADES = {
    "m": "minutes", "min": "minutes", "mins": "minutes",
    "minuto": "minutes", "minutos": "minutes",
    "h": "hours", "hr": "hours", "hrs": "hours", "hora": "hours", "horas": "hours",
    "dia": "days", "dias": "days",
    "semana": "weeks", "semanas": "weeks",
}

# Restos que sobram no assunto depois de tirar o gatilho e o horario.
_LIXO_INICIAL = re.compile(
    r"^\s*(?:de|do|da|pra|para|que|a|o)\s+", re.IGNORECASE
)


def _sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _limpar_assunto(texto):
    texto = _LIXO_INICIAL.sub("", texto.strip(" ,.!?;:-"))
    texto = re.sub(r"\s{2,}", " ", texto).strip(" ,.!?;:-")
    return texto[:200]


def parse(texto, tz_name, agora=None):
    """Devolve (epoch_ms, assunto) se o texto for um pedido de lembrete com horario.

    Devolve None quando nao ha gatilho, nao ha horario reconhecivel, ou o horario nao
    faz sentido - preferindo nao agendar a agendar errado.
    """
    if not texto:
        return None

    # A busca ignora acento, para "amanha"/"amanhã" e "as"/"às" caírem no mesmo padrao.
    # Tirar o acento nao muda o comprimento (cada letra acentuada vira uma letra), entao
    # os indices casam com o texto original e o assunto sai de la, acentuado.
    plano = _sem_acento(texto)
    if len(plano) != len(texto):  # pragma: no cover - texto com marca combinante solta
        texto = plano

    if not _GATILHO.search(plano):
        return None

    zona = _resolve_zone(tz_name)
    agora = agora or datetime.now(zona)

    achado = _RELATIVO.search(plano)
    if achado:
        quantidade = int(achado.group(1))
        unidade = _UNIDADES.get(achado.group(2).lower())
        if not unidade or quantidade < 1:
            return None
        alvo = agora + timedelta(**{unidade: quantidade})
        restante = texto[: achado.start()] + " " + texto[achado.end() :]
    else:
        achado = _ABSOLUTO.search(plano)
        if not achado:
            return None
        dia, hora, minuto = achado.group(1), int(achado.group(2)), int(achado.group(3) or 0)
        if hora > 23 or minuto > 59:
            return None

        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        dia = (dia or "").lower()
        if "depois" in dia:
            alvo += timedelta(days=2)
        elif "amanha" in dia:
            alvo += timedelta(days=1)
        elif alvo <= agora:
            # "as 9" quando ja passou das 9 quer dizer amanha.
            alvo += timedelta(days=1)
        restante = texto[: achado.start()] + " " + texto[achado.end() :]

    if alvo <= agora:
        return None

    assunto = _limpar_assunto(_GATILHO.sub("", restante, count=1))
    if not assunto:
        assunto = "o que voce pediu"

    return int(alvo.timestamp() * 1000), assunto
