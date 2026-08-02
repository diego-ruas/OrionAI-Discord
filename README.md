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
- recebe um comando com o prefixo (`o!ajuda` solto ja basta, sem `@`);
- recebe DM;
- a pessoa continua falando com ele logo depois de ter sido respondida, dentro da
  janela de `FOLLOWUP_WINDOW_SECONDS` (15s por padrao) - sem precisar de `@` em cada
  mensagem. O relogio reinicia a cada resposta dele, entao e tempo de silencio, nao
  duracao total da conversa. Se a pessoa mencionar ou responder outra pessoa nesse
  meio tempo, o bot entende que a conversa nao e com ele e fica calado.

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
PRESENCE=listening:{prefix}ajuda|watching:{guilds} servidores|watching:{reminders} lembretes agendados
```

Tipos: `playing`, `watching`, `listening`, `competing`, `custom` (ou `jogando`,
`assistindo`, `ouvindo`, `competindo`). Marcadores: `{prefix}`, `{guilds}`,
`{reminders}`, `{model}`. Uma entrada cujo numero der zero e pulada, para o bot nao
anunciar "0 lembretes agendados". Entrada mal formada e descartada com aviso no log em
vez de derrubar o boot. `PRESENCE` vazio desliga.

Nao da para fazer Rich Presence completo: o Discord aceita de bots apenas tipo, nome e
state - imagem, botao e party sao ignorados, porque dependem do RPC usado por
aplicativos de desktop.

## Memoria

Sao duas memorias diferentes:

- **Historico**: as ultimas `MEMORY_MAX_MESSAGES` mensagens do canal. Rotativo, e
  apagado por `o!reset`.
- **Longo prazo**: fatos que o proprio modelo decide salvar (apelido, profissao,
  projetos, preferencias de resposta) com a ferramenta `remember_fact`. Sobrevive a
  rotacao do historico e ao `o!reset`; e visivel com `o!memoria` e removivel com
  `o!esquecer`. Limite por canal em `MAX_FACTS_PER_CHANNEL`.

## Lembretes

Pedidos em linguagem natural no meio da conversa: "me lembra em 20 minutos de tirar o
bolo", "me avisa amanha as 9 da reuniao". O modelo chama a ferramenta
`schedule_reminder` e o bot entrega **no mesmo canal onde foi pedido**, marcando quem
pediu - inclusive em DM, se foi pedido em DM.

Os lembretes ficam no SQLite, nao em memoria, entao sobrevivem a restart do container.
Se o bot estiver fora do ar na hora marcada, o lembrete e entregue assim que ele volta,
com um aviso de que esta atrasado. `o!reset` **nao** apaga lembretes.

- `o!lembretes` lista os seus, com o numero de cada um.
- `o!cancelar <numero>` cancela. Ninguem cancela lembrete de outra pessoa.
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

- `o!ajuda` - lista os comandos e as formas de chamar o bot.
- `o!modo` - mostra o modo atual e as opcoes; `o!modo <nome>` troca (pede confirmacao
  por reacao). Modos: `padrao`, `realista`, `casual`, `sarcastico`, `professor`,
  `direto`. A escolha e por canal e fica salva no banco.
- `o!memoria` - lista o que o bot memorizou a longo prazo naquele canal.
- `o!esquecer <numero>` - apaga um item da memoria de longo prazo (o numero vem do
  `o!memoria`); `o!esquecer tudo` apaga todos, pedindo confirmacao.
- `o!lembretes` - lista seus lembretes agendados.
- `o!cancelar <numero>` - cancela um lembrete (o numero vem do `o!lembretes`).
- `o!parar` (ou `o!tchau`) - encerra a conversa na hora; em DM, silencia ate voce
  chamar pelo nome ou mandar um comando.
- `o!status` - modo ativo, modelos em uso, tamanho do historico e da memoria, lembretes
  pendentes, hora atual.
- `o!reset` - apaga o historico de conversa daquele canal (pede confirmacao). Nao
  apaga a memoria de longo prazo nem os lembretes.
