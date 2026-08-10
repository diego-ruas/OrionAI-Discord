import json

from ..config import config
from ..db import add_fact, forget_facts
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
]


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

    raise RuntimeError(f"Ferramenta desconhecida: {name}")
