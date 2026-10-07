import json

from ..config import config
from ..db import forget_facts
from . import crw, searxng, webfetch

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

    # SEARXNG_URL ligado: busca no SearXNG do proprio NAS e leitura de pagina feita
    # aqui mesmo (app/tools/webfetch.py). Desligado: fastCRW, como antes.
    if name == "web_search":
        search = searxng.web_search if config.searxng_url else crw.web_search
        results = await search(args.get("query"))
        return json.dumps(results, ensure_ascii=False)

    if name == "fetch_page":
        fetch = webfetch.fetch_page if config.searxng_url else crw.fetch_page
        return await fetch(args.get("url"))

    if name == "forget_fact":
        channel_id = context.get("channel_id")
        if not channel_id:
            raise RuntimeError("Sem canal para esquecer o fato.")
        # Sem isso a restricao dos comandos seria decorativa: bastaria pedir "esquece
        # tudo o que voce sabe" na conversa para o modelo apagar a memoria do canal.
        if not context.get("can_manage", False):
            return (
                "Nao apaguei: apagar a memoria do canal e restrito a quem modera. "
                "Diga isso a pessoa e siga a conversa normalmente."
            )
        # Texto injetado numa pagina/fato nao pode apagar a memoria inteira: consulta
        # curta ou ampla demais e recusada e a pessoa usa o comando, que pede confirmacao.
        query = (args.get("query") or "").strip()
        if len(query) < 3:
            return "Consulta curta demais; peca um trecho mais especifico do fato."
        removed = forget_facts(channel_id, query, max_matches=3)
        if removed is None:
            return (
                "Esse texto casa com fatos demais; use o comando de esquecer, que pede "
                "confirmacao."
            )
        if removed:
            return f"{removed} fato(s) esquecido(s)."
        return "Nenhum fato memorizado corresponde a esse texto."

    raise RuntimeError(f"Ferramenta desconhecida: {name}")
