# AGENTS.md

Guia para agentes de IA que forem mexer neste repositorio.

## O que e o projeto

Bot de Discord em Python (`discord.py`) que conversa usando modelos do OpenRouter,
com memoria persistente por canal em SQLite, ferramentas (busca web, leitura de
pagina, memoria de longo prazo) e visao/OCR em imagens. E so um chatbot: nao agenda
nada nem fala sozinho fora da conversa. Nao ha servidor web nem API exposta: o processo
e um cliente Discord de longa duracao (`python -m app.main`).

## Estrutura

```
app/
  main.py             # cliente discord.py, comandos e loop de mensagens
  config.py           # leitura de env vars e blocos fixos do system prompt
  db.py               # SQLite: historico, fatos, mensagens ambiente, mute
  openrouter.py       # chamadas ao modelo, tool-calling, visao e fallback de modelos
  permissions.py      # quem pode executar operacoes destrutivas
  tools/
    __init__.py       # definicoes e execucao das tools expostas ao modelo
    crw.py            # integracao com fastCRW (web_search / fetch_page)
  utils/
    clock.py          # hora local da conversa (TIMEZONE)
    image_processor.py# extracao/base64/recompressao de anexos de imagem
    ocr.py            # OCR local via tesseract (degrada sozinho se ausente)
    presence.py       # status/presenca do bot
    reply_format.py   # corte limpo, split em varias mensagens, delay de digitacao
tests/              # pytest das partes puras; config em pytest.ini
```

Config, Docker e docs: `.env.example`, `Dockerfile`, `docker-compose.yml`, `README.md`.

## Ambiente e execucao

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

- Obrigatorios no `.env`: `DISCORD_TOKEN`, `OPENROUTER_API_KEY`. `CRW_API_KEY` habilita
  busca/leitura de paginas.
- Toda nova env var deve ser documentada em `.env.example` (com comentario explicando
  o efeito e o default) e lida em `app/config.py` — nunca com `os.environ` espalhado
  pelo codigo.
- O banco fica em `./data/memory.sqlite` (volume no Docker). Nao commitar `data/`.
- Docker: `docker compose up -d --build`. O `Dockerfile` instala `tesseract-ocr`;
  sem ele o OCR se desliga sozinho, entao nao assuma que existe.

## Testes e verificacao

Ha uma suite de testes cobrindo as partes puras (`app/utils/clock.py`,
`reply_format.py`) e os blocos fixos do prompt, em `tests/`. Nao ha linter configurado.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Antes de dar uma mudanca como pronta:

- `python -m pytest` deve passar; se voce mexeu em `app/utils`, adicione teste.
- `python -m compileall app` para pegar erro de sintaxe no que nao tem teste.
- Se a mudanca toca o fluxo de mensagem, rode o bot de fato (`python -m app.main`) e
  exercite o caminho no Discord. Nao afirme que funciona sem ter rodado.
- Teste nao pode depender de rede, do Discord nem do relogio. Nao escreva teste que
  passa so em certa hora do dia.
- Nao introduza dependencia nova sem adicionar em `requirements.txt` com comentario
  dizendo para que serve e o que acontece sem ela (padrao ja seguido no arquivo).

## Convencoes de codigo

- **Idioma:** codigo, comentarios, docstrings, mensagens de commit e todo texto
  mostrado ao usuario em portugues, **sem acentos** no codigo e nos comentarios
  (o repositorio ja e assim; mantenha).
- **Comentarios explicam o porque, nao o que.** O padrao do projeto e comentario que
  registra a razao de uma decisao ou a armadilha evitada (ver `db.py`,
  `permissions.py`, `openrouter.py`). Nao adicione comentario narrando linha obvia.
- Estilo simples: funcoes de modulo, sem classes desnecessarias, sem type hints
  (o codigo atual nao usa) e sem framework extra.
- `async`/`await` em todo I/O dentro do loop do discord.py. Nada de chamada
  bloqueante no event loop.
- Nomes de comando ficam em `COMMAND_NAMES` (`app/main.py`); o prefixo e
  configuravel (`config.command_prefix`), entao nunca escreva o prefixo cru em
  mensagem ao usuario — interpole `prefix`.

## Regras de comportamento do bot (nao quebrar)

- **Tom descontraido e fixo.** `PLAYFUL_INSTRUCTIONS` em `config.py` e sempre anexado
  depois do system prompt do usuario e prevalece sobre ele: humor leve, ironia branda,
  giria e emoji com parcimonia. Nao transforme isso em modo ligavel. Os limites do
  bloco (humor nunca as custas de alguem, nunca a custa da informacao correta, sem
  piada forcada) fazem parte da regra, nao sao enfeite.
- **Conteudo de internet e nao confiavel.** Resultados de tools em `UNTRUSTED_TOOLS`
  (`web_search`, `fetch_page`) voltam ao modelo isolados pelo
  `UNTRUSTED_TOOL_RESULT_TEMPLATE`. Toda tool nova que traga dado externo deve entrar
  nesse conjunto.
- **Mencoes restritas.** O cliente e criado com `allowed_mentions` bloqueando
  `@everyone`, `@here` e cargos. Nao afrouxe isso.
- **Operacoes destrutivas passam por `can_manage`** (`permissions.py`): limpar
  historico e apagar memoria de longo prazo. Leitura e conversa continuam livres. Em
  DM e sempre permitido.
- **Nao prometer o que nao aconteceu.** O bot nao agenda nada nem fala sozinho fora da
  conversa (`NO_SCHEDULING_INSTRUCTIONS` em `config.py`). Nao reintroduza lembrete,
  cron ou qualquer promessa de mensagem futura sem pedido explicito.
- **Rodape do codigo nao entra no historico.** O que o codigo anexa a resposta e
  interface, nao fala do modelo: vai para o Discord, e o texto gravado em `db` e o
  original. `strip_code_footers` (`main.py`) ainda limpa copias que o modelo tenha
  aprendido de historicos antigos.
- **Falha de modelo nao pode virar silencio.** `openrouter.py` tenta
  `config.model` e depois `config.fallback_models`, e `RateLimitError` sobe para o
  `main.py` avisar a pessoa. Nao engula a excecao nem responda vazio.
- **Migracao de banco:** `_migrate_legacy_messages` (`db.py`) renomeia a tabela antiga
  para `messages_legacy_v<n>` em vez de apagar. Qualquer mudanca de schema deve seguir
  o mesmo principio: nunca destruir dados do usuario numa atualizacao.

## Git

- Branch principal: `master`.
- Mensagens de commit em portugues, no imperativo e curtas, no estilo do historico
  (ex.: "Restringir apagar dados a quem modera").
- Commitar ou dar push apenas quando pedido.
