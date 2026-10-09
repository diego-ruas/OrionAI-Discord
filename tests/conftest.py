import os

# Config e instanciado na importacao e exige as chaves obrigatorias; teste nao deve
# depender de um .env local.
os.environ.setdefault("DISCORD_TOKEN", "token-de-teste")
os.environ.setdefault("OPENROUTER_API_KEY", "chave-de-teste")
