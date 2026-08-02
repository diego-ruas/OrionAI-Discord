# OrionAI (Python)

Bot de Discord com IA gratuita via OpenRouter e memoria persistente por canal, em Python.
A versao original em Node.js foi removida do repositorio.

O repositorio ja se chamou `NovoBotRoberto`; os identificadores Docker usam
`orionai-discord` (minusculo, exigencia do Docker para nome de imagem e projeto).

## Estrutura

```
app/
  main.py            # cliente discord.py e loop de mensagens
  config.py           # variaveis de ambiente, personas e blocos fixos do prompt
  db.py               # SQLite: historico, fatos, contexto do canal e lembretes
  openrouter.py        # chamadas ao OpenRouter com tools, visao e fallback de modelos
  tools/
    __init__.py        # tools: web_search, fetch_page, remember_fact, forget_fact, schedule_reminder
    crw.py              # integracao com fastCRW
  utils/
    image_processor.py  # download/base64 de anexos de imagem
    reply_format.py     # corte limpo e quebra da resposta em varias mensagens
    clock.py            # data/hora local e interpretacao de horarios de lembrete
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

Preencha o `.env` com `DISCORD_TOKEN` e `OPENROUTER_API_KEY` (obrigatorios) e, opcionalmente,
`CRW_API_KEY` para as ferramentas de busca/leitura de paginas.

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
   entao sobrevivem a reinicios/atualizacoes do container.

### Opcao B - Docker Compose manual (SSH no NAS)

```bash
cd /caminho/para/OrionAI-Discord
cp .env.example .env   # edite com suas chaves
docker compose up -d --build
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
- recebe DM;
- a pessoa continua falando com ele logo depois de ter sido respondida, dentro da
  janela de `FOLLOWUP_WINDOW_SECONDS` (15s por padrao) - sem precisar de `@` em cada
  mensagem. O relogio reinicia a cada resposta dele, entao e tempo de silencio, nao
  duracao total da conversa. Se a pessoa mencionar ou responder outra pessoa nesse
  meio tempo, o bot entende que a conversa nao e com ele e fica calado.

Para encerrar antes da janela expirar, use `!parar` (ou `!tchau`):

- **em canal**: encerra a conversa em andamento so de quem pediu, e o bot volta a
  exigir `@`. Nao silencia o bot para as outras pessoas do canal.
- **em DM**: como ali ele responderia toda mensagem, o `!parar` liga um modo
  silencioso de verdade, guardado no banco (sobrevive a restart). Ele so volta a
  falar quando voce chamar pelo nome ou mandar qualquer `!comando` - as duas coisas
  que continuam funcionando com ele calado.

As demais mensagens do canal nao geram resposta, mas as ultimas
`AMBIENT_CONTEXT_MESSAGES` ficam guardadas como contexto ("do que estavam falando")
para quando ele for chamado. Coloque `AMBIENT_CONTEXT_MESSAGES=0` para desligar isso.

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

## Memoria

Sao duas memorias diferentes:

- **Historico**: as ultimas `MEMORY_MAX_MESSAGES` mensagens do canal. Rotativo, e
  apagado por `!reset`.
- **Longo prazo**: fatos que o proprio modelo decide salvar (apelido, profissao,
  projetos, preferencias de resposta) com a ferramenta `remember_fact`. Sobrevive a
  rotacao do historico e ao `!reset`; e visivel com `!memoria` e removivel com
  `!esquecer`. Limite por canal em `MAX_FACTS_PER_CHANNEL`.

## Lembretes

Pedidos em linguagem natural no meio da conversa: "me lembra em 20 minutos de tirar o
bolo", "me avisa amanha as 9 da reuniao". O modelo chama a ferramenta
`schedule_reminder` e o bot entrega **no mesmo canal onde foi pedido**, marcando quem
pediu - inclusive em DM, se foi pedido em DM.

Os lembretes ficam no SQLite, nao em memoria, entao sobrevivem a restart do container.
Se o bot estiver fora do ar na hora marcada, o lembrete e entregue assim que ele volta,
com um aviso de que esta atrasado. `!reset` **nao** apaga lembretes.

- `!lembretes` lista os seus, com o numero de cada um.
- `!cancelar <numero>` cancela. Ninguem cancela lembrete de outra pessoa.
- Limites em `MAX_REMINDERS_PER_USER` e `MAX_REMINDER_DAYS`; a frequencia de
  verificacao em `REMINDER_CHECK_SECONDS`.

## Modelos e falhas

O bot tenta `OPENROUTER_MODEL` e, se ele falhar por qualquer motivo (rate limit, erro
HTTP, resposta vazia), desce a lista de `OPENROUTER_FALLBACK_MODELS` na ordem. Com
modelos `:free` isso nao e opcional: um unico 429 sem fallback ja vira "nao consegui
responder". Todos os modelos da cadeia precisam suportar tool calling, porque as
ferramentas vao em toda chamada.

Quando algo falha, o log traz o motivo real: `[openrouter] Falha com <modelo>: ...`
com o status HTTP e o corpo da resposta, e `[bot]` com o traceback completo.

## Imagens

Mande uma imagem (jpeg/png/gif/webp) junto da mensagem e ela e enviada ao modelo de
visao configurado em `OPENROUTER_VISION_MODEL`. Nessas chamadas as ferramentas ficam
desligadas, porque a maioria dos modelos de visao gratuitos nao as suporta.

## Comandos do bot

Todos funcionam mencionando o bot no canal, ou direto em DM:

- `!ajuda` - lista os comandos e as formas de chamar o bot.
- `!modo` - mostra o modo atual e as opcoes; `!modo <nome>` troca (pede confirmacao
  por reacao). Modos: `padrao`, `realista`, `casual`, `sarcastico`, `professor`,
  `direto`. A escolha e por canal e fica salva no banco.
- `!memoria` - lista o que o bot memorizou a longo prazo naquele canal.
- `!esquecer <numero>` - apaga um item da memoria de longo prazo (o numero vem do
  `!memoria`); `!esquecer tudo` apaga todos, pedindo confirmacao.
- `!lembretes` - lista seus lembretes agendados.
- `!cancelar <numero>` - cancela um lembrete (o numero vem do `!lembretes`).
- `!parar` (ou `!tchau`) - encerra a conversa na hora; em DM, silencia ate voce
  chamar pelo nome ou mandar um comando.
- `!status` - modo ativo, modelos em uso, tamanho do historico e da memoria, lembretes
  pendentes, hora atual.
- `!reset` - apaga o historico de conversa daquele canal (pede confirmacao). Nao
  apaga a memoria de longo prazo nem os lembretes.
