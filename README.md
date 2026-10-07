# OrionAI (Python)

Bot de Discord com IA gratuita via OpenRouter e memoria persistente por canal, em Python.
A versao original em Node.js foi removida do repositorio.

O repositorio ja se chamou `NovoBotRoberto`; os identificadores Docker usam
`orionai-discord` (minusculo, exigencia do Docker para nome de imagem e projeto).

## Estrutura

```
app/
  main.py            # cliente discord.py, comandos e loop de mensagens
  config.py           # variaveis de ambiente e blocos fixos do prompt
  db.py               # SQLite: historico, fatos e contexto do canal
  memory.py           # curadoria da memoria em segundo plano: fatos e resumo
  openrouter.py        # chamadas ao OpenRouter com tools, visao e fallback de modelos
  permissions.py       # quem pode executar operacoes destrutivas
  tools/
    __init__.py        # tools: web_search, fetch_page, forget_fact
    crw.py              # busca/leitura de paginas via fastCRW
    searxng.py          # busca via SearXNG proprio
    webfetch.py         # leitura de paginas feita no proprio bot, com protecao de SSRF
  utils/
    clock.py            # data/hora local da conversa
    http_client.py      # sessao HTTP compartilhada (Keep-Alive)
    image_processor.py  # download/base64 de anexos de imagem
    ocr.py              # OCR local via tesseract
    presence.py         # status/presenca do bot
    reply_format.py     # corte limpo e quebra da resposta em varias mensagens
    memory_format.py    # prompt e parsing da curadoria
```

Bancos criados por versoes antigas do bot (memoria por usuario, tabela `messages` sem
`channel_id`) sao detectados na inicializacao: a tabela antiga e renomeada para
`messages_legacy_v1` - nada e apagado - e o schema atual e criado do zero.

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

Preencha o `.env` com `DISCORD_TOKEN` e `OPENROUTER_API_KEY` (obrigatorios). Para as
ferramentas de busca/leitura de paginas, use `SEARXNG_URL` (SearXNG proprio, sem chave) ou
`CRW_API_KEY` (fastCRW).

## Testes

Cobrem as partes deterministicas: formatacao da resposta (`reply_format`), data/hora
(`clock`), os blocos fixos do prompt e o parsing das variaveis de ambiente. Nao
precisam de token, rede nem banco.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Docker / CasaOS

O projeto inclui `Dockerfile` e `docker-compose.yml` prontos para rodar num NAS com CasaOS.

### Opcao A - Instalacao customizada no CasaOS

1. Copie a pasta do projeto para o NAS (ex: via Samba/SFTP).
2. No CasaOS, va em **App Store > Custom Install** (instalar via Docker Compose).
3. Cole o conteudo de `docker-compose.yml` ou aponte para a pasta do projeto.
4. Antes de subir, crie o arquivo `.env` na raiz do projeto (copia de `.env.example`) com
   suas chaves reais - o CasaOS tambem permite preencher as variaveis listadas em
   `x-casaos.envs` diretamente na interface.
5. Inicie o app. Os dados de memoria ficam persistidos em `./data` (montado como volume),
   entao sobrevivem a reinicios/atualizacoes do container. O container roda como usuario
   sem root (uid 1000): rode `mkdir -p data && sudo chown 1000:1000 data` no NAS antes de
   iniciar, senao o bot nao consegue abrir o SQLite.

### Opcao B - Docker Compose manual (SSH no NAS)

```bash
cd /caminho/para/OrionAI-Discord
cp .env.example .env   # edite com suas chaves
mkdir -p data && sudo chown 1000:1000 data   # o container roda sem root (uid 1000)
docker compose up -d --build
```

O container roda como usuario sem root (uid 1000) e precisa escrever o SQLite em
`./data`. Antes do primeiro `up` (e ao atualizar um deploy antigo que rodava como root):

```bash
mkdir -p data && sudo chown 1000:1000 data
```

Para atualizar apos alterar o codigo:

```bash
docker compose up -d --build
```

Para ver logs:

```bash
docker compose logs -f
```

## Como o bot entra na conversa

O bot responde quando:

- e mencionado com `@`;
- alguem responde (reply) uma mensagem dele;
- e chamado pelo nome no meio da frase (configuravel em `BOT_NAMES`);
- recebe um comando com o prefixo (`o!ajuda` solto ja basta, sem `@`);
- recebe DM;
- a pessoa continua falando com ele logo depois de ter sido respondida, dentro da
  janela de `FOLLOWUP_WINDOW_SECONDS` (15s por padrao) - sem precisar de `@` em cada
  mensagem. O relogio reinicia a cada resposta dele, entao e tempo de silencio, nao
  duracao total da conversa. Se a pessoa mencionar ou responder outra pessoa nesse
  meio tempo, o bot entende que a conversa nao e com ele e fica calado. Com
  `JEV_FOLLOWUP_THRESHOLD` acima de 0, o Jev (modelo de decisao da TypeSafe) ainda
  confere se a mensagem e mesmo pro bot antes de ele responder.

Jev tambem pode julgar cada mensagem antes do modelo de conversa (tudo desligado por
padrao, ver `.env.example`): `JEV_INTENT_CONFIDENCE` classifica o pedido (conversa,
busca, link, memoria) para oferecer so as ferramentas que fazem sentido e estima o
tamanho da resposta; `JEV_INJECTION_THRESHOLD` avisa o modelo quando a mensagem parece
tentar mudar as regras do bot. Se o Jev falhar ou ficar na duvida, o bot segue como antes.

Para encerrar antes da janela expirar, use `o!parar` (ou `o!tchau`):

- **em canal**: encerra a conversa em andamento so de quem pediu, e o bot volta a
  exigir `@`. Nao silencia o bot para as outras pessoas do canal.
- **em DM**: como ali ele responderia toda mensagem, o `o!parar` liga um modo
  silencioso de verdade, guardado no banco (sobrevive a restart). Ele so volta a
  falar quando voce chamar pelo nome ou mandar qualquer `o!comando` - as duas coisas
  que continuam funcionando com ele calado.

As demais mensagens do canal nao geram resposta, mas as ultimas
`AMBIENT_CONTEXT_MESSAGES` ficam guardadas como contexto ("do que estavam falando")
para quando ele for chamado. Coloque `AMBIENT_CONTEXT_MESSAGES=0` para desligar isso.

## Tom

O bot e descontraido: piada, trocadilho, ironia leve, gíria e emoji ocasional fazem
parte do jeito dele falar, e ele devolve provocacao de quem provoca. Isso nao e um modo
que se liga e desliga - a regra de tom e um bloco fixo (`PLAYFUL_INSTRUCTIONS`) anexado
depois do `SYSTEM_PROMPT`, entao prevalece sobre o que estiver na env var.

O humor tem limite, e ele e a parte importante da regra:

- a graca esta no jeito de dizer, nunca no conteudo - o bot nao inventa informacao para
  render uma piada, e corta o humor quando ele atrapalha a clareza;
- brincadeira e com a situacao, nunca as custas de quem perguntou, e some quando a
  pessoa esta frustrada, perdida ou desabafando;
- piada forcada em toda mensagem cansa: sem gracinha na manga, ele so responde bem;
- ele nao puxa assunto sozinho nem comenta conversa alheia so para aparecer - continua
  respondendo apenas quando e chamado.

## Conversa natural

Alguns comportamentos existem so para a conversa nao soar como saida de maquina:

- respostas longas saem quebradas em varias mensagens curtas nos paragrafos, com
  indicador de digitacao e pausa proporcional ao tamanho entre elas
  (`SPLIT_REPLIES`, `MAX_REPLY_MESSAGES`, `TYPING_CHARS_PER_SECOND`);
- blocos de codigo nunca sao partidos no meio;
- o bot responde sem pingar o autor, mantendo o link da mensagem sem a notificacao;
- um bloco fixo do prompt (em `app/config.py`) corta os vicios tipicos de texto
  gerado: repetir a pergunta, abrir com "Claro!", fechar com "espero ter ajudado",
  listar em topicos uma conversa casual, perguntar algo de volta em toda mensagem;
- o bot sabe a data, a hora e o periodo do dia (`TIMEZONE`), o canal e o servidor
  em que esta;
- quando alguem responde a mensagem de outra pessoa, o trecho citado entra no
  contexto.

## Presenca

O "Assistindo/Ouvindo ..." embaixo do nome do bot alterna entre frases alimentadas por
dados reais, a cada `PRESENCE_ROTATE_SECONDS`. Configuracao em `PRESENCE`, entradas
`tipo:texto` separadas por `|`:

```bash
PRESENCE=listening:{prefix}ajuda|watching:{guilds} servidores
```

Tipos: `playing`, `watching`, `listening`, `competing`, `custom` (ou `jogando`,
`assistindo`, `ouvindo`, `competindo`). Marcadores: `{prefix}`, `{guilds}`,
`{model}`. Uma entrada cujo numero der zero e pulada, para o bot nao anunciar
"0 servidores". Entrada mal formada e descartada com aviso no log em
vez de derrubar o boot. `PRESENCE` vazio desliga.

Nao da para fazer Rich Presence completo: o Discord aceita de bots apenas tipo, nome e
state - imagem, botao e party sao ignorados, porque dependem do RPC usado por
aplicativos de desktop.

## Quem pode apagar

Apagar dados de um canal (`o!reset` e `o!esquecer`) e restrito a quem tem permissao de
**administrador**, **gerenciar servidor** ou **gerenciar mensagens** - mais o dono do
servidor e quem tiver um cargo listado em `ADMIN_ROLES` (nome ou id).

Ler continua livre: `o!memoria`, `o!status`, os botoes do embed e conversar valem para
todo mundo.

A ferramenta `forget_fact` obedece a mesma regra. Sem isso a restricao seria
decorativa: bastaria pedir "esquece tudo o que voce sabe" na conversa para o modelo
apagar a memoria do canal sem passar por comando nenhum.

Em DM a restricao nao se aplica - nao ha hierarquia ali, e o historico e da propria
pessoa; bloquear trancaria alguem para fora dos proprios dados.

A permissao e avaliada no canal em que o comando foi dado, entao overwrites de canal
(conceder ou negar "gerenciar mensagens") contam. Com a memoria cheia, o bot para de
memorizar em vez de expulsar fatos antigos, e so quem modera abre espaco. Assim ninguem
apaga a memoria do canal enchendo-a.

## Memoria

Sao duas memorias diferentes:

- **Historico**: as ultimas `MEMORY_MAX_MESSAGES` mensagens vao inteiras para o modelo.
- **Resumo**: o que sai dessa janela e incorporado a um resumo do canal, em lotes de 10
  ou mais mensagens. E apagado por `o!reset`.
- **Longo prazo**: fatos captados automaticamente cerca de 45s depois que a conversa
  para, por uma chamada separada ao modelo, sem atrasar a resposta. Sao visiveis com
  `o!memoria` e removiveis com `o!esquecer`. Com `MAX_FACTS_PER_CHANNEL` cheio, nada e
  expulso; fato novo e descartado. Cada pessoa pode ter criado no maximo
  `MAX_FACTS_PER_AUTHOR` desses fatos, para ninguem ocupar todos os espacos sozinha.

## Defesas

- Fatos e resumo da memoria vem de conversa de terceiros: entram no prompt como dado
  marcado (`NAO SAO INSTRUCOES`), em linha unica e sem colchetes nem `<`.
- Limite de mensagens por pessoa (`RATE_LIMIT_MESSAGES` / `RATE_LIMIT_WINDOW_SECONDS`),
  checado antes de baixar imagem, rodar OCR ou chamar o modelo.
- `fetch_page` so aceita URL http(s) curta, sem IP literal, localhost, porta fora de
  80/443 ou credenciais; no maximo 3 chamadas de ferramenta por rodada.
- Com `SEARXNG_URL` (padrao do compose) o bot le paginas a partir do proprio host, entao
  a leitura e fechada para a rede interna: sessao propria que recusa, ja na resolucao de
  DNS, host que aponte para IP privado, loopback ou link-local; redirecionamentos sao
  seguidos a mao e revalidados; so `text/html` e `text/plain`, ate 2 MB e 20s.
- `forget_fact` (ferramenta) recusa consulta com menos de 3 caracteres ou que case com
  mais de 3 fatos; o curinga `%`/`_` do LIKE e escapado.
- Uma resposta menciona no maximo 3 usuarios; `o!memoria` e `Esqueci:` nunca mencionam.
- Imagens: ate 4 por mensagem, 25 Mpx cada (bomba de descompressao vira erro) e OCR
  com timeout de 15s.

## Nada de agendamento

O bot so existe dentro da conversa: ele nao agenda lembretes nem manda mensagem
sozinho depois. Um bloco fixo do prompt (`NO_SCHEDULING_INSTRUCTIONS` em
`app/config.py`) proibe prometer "te aviso mais tarde", porque a promessa nunca seria
cumprida e a pessoa ficaria esperando.

## Modelos e falhas

O bot tenta `OPENROUTER_MODEL` e, se ele falhar por qualquer motivo (rate limit, erro
HTTP, resposta vazia), desce a lista de `OPENROUTER_FALLBACK_MODELS` na ordem. Com
modelos `:free` isso nao e opcional: um unico 429 sem fallback ja vira "nao consegui
responder". Todos os modelos da cadeia precisam suportar tool calling, porque as
ferramentas vao em toda chamada.

Quando algo falha, o log traz o motivo real: `[openrouter] Falha com <modelo>: ...`
com o status HTTP e o corpo da resposta, e `[bot]` com o traceback completo.

## Imagens

Mande uma imagem (jpeg/png/gif/webp) junto da mensagem. O caminho tem tres etapas, e
as duas primeiras acontecem na propria maquina:

1. **Reduz** para `VISION_MAX_IMAGE_PX` (1024px) e recomprime em JPEG. Uma foto de
   celular sai de ~11 MB para ~0,2 MB - o base64 de uma foto crua desperdicava token
   a toa e podia estourar o limite da requisicao.
2. **Le o texto com OCR local** (Tesseract, `OCR_ENABLED`). Print de codigo, de erro
   ou de conversa - o caso mais comum no Discord - e resolvido aqui: leva menos de um
   segundo, gasta ~100 MB de RAM e **a imagem nao sai da rede**. Se o OCR achar pelo
   menos `OCR_MIN_CHARS` caracteres, o texto entra na conversa e a etapa 3 e pulada
   (`OCR_SKIPS_VISION`).
3. **Modelo de visao**, so para o que o OCR nao resolve (foto, meme, grafico). Por
   padrao (`VISION_DESCRIBE_ONLY`) ele apenas **descreve** a imagem, recebendo um
   prompt de ~70 tokens e mais nada; quem redige a resposta e o modelo de texto de
   sempre, a partir dessa descricao.

A etapa 3 em duas fases existe por tres motivos: o provedor de visao deixa de receber
o system prompt inteiro, o historico do canal e os fatos memorizados (~60% menos
tokens); a resposta final mantem a persona e pode usar as ferramentas, o que nao
acontecia quando o modelo de visao respondia direto; e a conversa nao vaza para um
provedor diferente do de texto. Com `VISION_DESCRIBE_ONLY=false` volta ao modo de uma
chamada so.

O texto lido por OCR entra marcado como dado, nunca como instrucao - a mesma protecao
usada em conteudo vindo da web, ja que uma imagem pode conter texto tentando se passar
por comando.

### Processando tudo localmente

Para nenhuma imagem sair da maquina, `VISION_ENABLED=false`: o bot responde com o que
o OCR leu e avisa quando nao conseguiu enxergar.

Para ter descricao de imagem de verdade sem usar a nuvem, aponte a visao para um
servidor compativel com a API da OpenAI:

```bash
VISION_API_BASE=http://192.168.0.10:11434/v1   # Ollama, LM Studio, llama.cpp
VISION_MODEL=moondream
```

### Usando o Gemini so para as imagens

O mesmo mecanismo serve para trocar de provedor apenas na visao, mantendo o texto no
OpenRouter:

```bash
VISION_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai
VISION_API_KEY=sua_chave_do_gemini
VISION_MODEL=gemini-3.5-flash-lite
```

Sobre o custo: o Gemini cobra 258 tokens quando os dois lados da imagem tem no maximo
384px, e passa a cobrar por ladrilho acima disso - 4 ladrilhos (1032 tokens) para
qualquer imagem 4:3 maior, 6 para 16:9. Como o corte e por ladrilho e nao por pixel,
`VISION_MAX_IMAGE_PX` em 1024, 768 ou 512 custa exatamente o mesmo; so 384 fica mais
barato, perdendo detalhe. Somado ao OCR (que evita a chamada inteira nos prints) e ao
modo de descricao, uma imagem sai por volta de 1.100 tokens em vez de 2.700.

Um aviso de dimensionamento: modelo de visao em CPU e pesado. Num NAS sem GPU e com
8 GB, mesmo o moondream (~1.7B) ocupa 2-3 GB e leva de 30s a alguns minutos por
imagem, com o bot parado esperando. Se for por esse caminho, rode o Ollama numa
maquina com GPU e aponte o bot para ela pela rede - nao no proprio NAS.

## Comandos do bot

Comando com o prefixo ja e um endereco direto ao bot: funciona solto no canal, sem
precisar de `@`, e tambem em DM. Vale so para comando existente - `o!naoexiste` nao
acorda o bot.

`o!` e o padrao de `COMMAND_PREFIX`; `help` e alias de `ajuda`.

- `o!ajuda` - embed com os comandos e botoes de Memoria, Status e Parar. Clicar
  responde so para quem clicou (ephemeral), sem digitar comando.
- `o!memoria` - lista o que o bot memorizou a longo prazo naquele canal.
- `o!esquecer <numero>` - apaga um item da memoria de longo prazo (o numero vem do
  `o!memoria`); `o!esquecer tudo` apaga todos, pedindo confirmacao.
- `o!parar` (ou `o!tchau`) - encerra a conversa na hora; em DM, silencia ate voce
  chamar pelo nome ou mandar um comando.
- `o!status` - modelos em uso, tamanho do historico e da memoria, hora atual.
- `o!reset` - apaga o historico de conversa daquele canal (pede confirmacao). Nao
  apaga a memoria de longo prazo.
