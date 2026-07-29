# Novo Bot Roberto (Python)

Bot de Discord com IA gratuita via OpenRouter e memoria persistente por canal, em Python.
A versao original em Node.js foi removida do repositorio.

## Estrutura

```
app/
  main.py            # cliente discord.py e loop de mensagens
  config.py           # leitura das variaveis de ambiente
  db.py               # historico em SQLite (sqlite3 stdlib)
  openrouter.py        # chamadas ao OpenRouter com suporte a tools e fallback de modelos
  tools/
    __init__.py        # definicoes de tools (web_search, fetch_page)
    crw.py              # integracao com fastCRW
  utils/
    image_processor.py  # download/base64 de anexos de imagem (preparado para vision)
```

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
cd /caminho/para/NovoBotRoberto
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

## Comandos do bot

- Mencione o bot ou mande DM para conversar.
- `!reset` (mencionando o bot, ou em DM) apaga o historico daquele canal.
