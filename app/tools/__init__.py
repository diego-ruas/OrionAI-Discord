import json

from .crw import fetch_page, web_search

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
]


async def run_tool(name, args):
    if name == "web_search":
        results = await web_search(args.get("query"))
        return json.dumps(results, ensure_ascii=False)
    if name == "fetch_page":
        return await fetch_page(args.get("url"))
    raise RuntimeError(f"Ferramenta desconhecida: {name}")
