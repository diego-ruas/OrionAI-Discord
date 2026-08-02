import json

from .. import db
from ..config import config
from ..db import add_fact, forget_facts
from ..utils.clock import describe_timestamp, now_ms, parse_local_datetime
from .crw import fetch_page, web_search

# Ferramentas cujo resultado vem da internet: conteudo nao confiavel, que precisa ser
# isolado com marcadores antes de voltar para o modelo (ver app/openrouter.py).
UNTRUSTED_TOOLS = {"web_search", "fetch_page"}

tool_definitions = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Pesquisa na internet e retorna uma lista de resultados (titulo e url). "
                "Use quando precisar de informacoes atuais ou que voce nao tem certeza."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termos de busca"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Busca o conteudo em texto de uma URL especifica (por exemplo, uma URL "
                "retornada pelo web_search) para ler os detalhes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa a ser lida"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": (
                "Salva na memoria de longo prazo um fato que vale lembrar em conversas "
                "futuras deste canal (preferencias, apelido, profissao, projetos, "
                "decisoes, como a pessoa gosta de ser respondida). Use de forma "
                "silenciosa, sem avisar que esta salvando. Um fato por chamada, em uma "
                "frase curta. Nao salve trivialidades nem dados sensiveis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "O fato em uma frase curta, ex: 'prefere respostas curtas'",
                    },
                    "about": {
                        "type": "string",
                        "description": (
                            "Nome do usuario a quem o fato se refere, exatamente como "
                            "aparece na conversa. Use 'canal' para fatos do grupo."
                        ),
                    },
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": (
                "Apaga da memoria de longo prazo os fatos que contenham um texto. Use "
                "quando a pessoa pedir para voce esquecer ou corrigir algo que voce "
                "tinha memorizado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Trecho do fato a esquecer, ex: 'mora em Curitiba'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_reminder",
            "description": (
                "Agenda um lembrete para ser entregue neste mesmo canal, marcando quem "
                "pediu. Use quando a pessoa pedir para ser lembrada ou avisada de algo "
                "mais tarde. Informe in_minutes para pedidos relativos ('em 2 horas') ou "
                "at para dia e hora especificos - um dos dois, nunca os dois juntos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Assunto do lembrete, curto e na segunda pessoa, ex: "
                            "'tomar o remedio'"
                        ),
                    },
                    "in_minutes": {
                        "type": "integer",
                        "description": "Minutos a partir de agora, ex: 120 para 2 horas",
                    },
                    "at": {
                        "type": "string",
                        "description": (
                            "Dia e hora no formato 'AAAA-MM-DD HH:MM' (24h), no fuso "
                            "local. Aceita tambem so 'HH:MM' para o proximo horario."
                        ),
                    },
                },
                "required": ["text"],
            },
        },
    },
]


def _schedule_reminder(args, context):
    channel_id = context.get("channel_id")
    user_id = context.get("user_id")
    if not channel_id or not user_id:
        raise RuntimeError("Sem canal ou usuario para agendar o lembrete.")

    text = (args.get("text") or "").strip()
    if not text:
        return "Nao agendei: o lembrete precisa de um assunto."

    if db.count_pending_reminders(user_id) >= config.max_reminders_per_user:
        return (
            f"Nao agendei: essa pessoa ja tem {config.max_reminders_per_user} lembretes "
            f"pendentes, o maximo permitido. Ela precisa cancelar algum com "
            f"{config.command_prefix}cancelar."
        )

    in_minutes = args.get("in_minutes")
    at = (args.get("at") or "").strip()

    if in_minutes is not None and at:
        return "Nao agendei: use in_minutes OU at, nunca os dois na mesma chamada."

    now = now_ms()
    if in_minutes is not None:
        try:
            minutes = int(in_minutes)
        except (TypeError, ValueError):
            return f"Nao agendei: '{in_minutes}' nao e um numero de minutos valido."
        if minutes < 1:
            return "Nao agendei: o lembrete tem que ser para pelo menos 1 minuto adiante."
        remind_at = now + minutes * 60_000
    elif at:
        try:
            remind_at = parse_local_datetime(at, config.timezone)
        except ValueError as err:
            return f"Nao agendei: {err}. Pergunte o horario de novo, mais claro."
    else:
        return "Nao agendei: falta in_minutes ou at."

    if remind_at <= now:
        return (
            "Nao agendei: esse horario ja passou. Confirme com a pessoa para quando ela "
            "quer o lembrete."
        )

    horizon = now + config.max_reminder_days * 86_400_000
    if remind_at > horizon:
        return (
            f"Nao agendei: nao consigo agendar para mais de {config.max_reminder_days} "
            "dias a frente."
        )

    db.add_reminder(channel_id, user_id, context.get("username"), text[:500], remind_at)
    return (
        f"Lembrete agendado para {describe_timestamp(remind_at, config.timezone)}: {text}"
    )


async def run_tool(name, args, context=None):
    context = context or {}

    if name == "web_search":
        results = await web_search(args.get("query"))
        return json.dumps(results, ensure_ascii=False)

    if name == "fetch_page":
        return await fetch_page(args.get("url"))

    if name == "remember_fact":
        channel_id = context.get("channel_id")
        if not channel_id:
            raise RuntimeError("Sem canal para salvar o fato.")
        saved = add_fact(
            channel_id,
            args.get("about"),
            args.get("fact"),
            config.max_facts_per_channel,
        )
        return "Fato memorizado." if saved else "Esse fato ja estava memorizado."

    if name == "forget_fact":
        channel_id = context.get("channel_id")
        if not channel_id:
            raise RuntimeError("Sem canal para esquecer o fato.")
        # Sem isso a restricao dos comandos seria decorativa: bastaria pedir "esquece
        # tudo o que voce sabe" na conversa para o modelo apagar a memoria do canal.
        if not context.get("can_manage", True):
            return (
                "Nao apaguei: apagar a memoria do canal e restrito a quem modera. "
                "Diga isso a pessoa e siga a conversa normalmente."
            )
        removed = forget_facts(channel_id, args.get("query"))
        if removed:
            return f"{removed} fato(s) esquecido(s)."
        return "Nenhum fato memorizado corresponde a esse texto."

    if name == "schedule_reminder":
        return _schedule_reminder(args, context)

    raise RuntimeError(f"Ferramenta desconhecida: {name}")
