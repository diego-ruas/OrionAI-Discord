import os

from dotenv import load_dotenv

load_dotenv()


def _required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


class Config:
    def __init__(self):
        self.discord_token = _required("DISCORD_TOKEN")
        self.openrouter_api_key = _required("OPENROUTER_API_KEY")
        self.crw_api_key = os.environ.get("CRW_API_KEY", "")
        self.model = os.environ.get("OPENROUTER_MODEL", "tencent/hy3:free")
        self.vision_model = os.environ.get(
            "OPENROUTER_VISION_MODEL", "google/gemma-4-26b-a4b-it:free"
        )
        self.fallback_models = [
            m.strip()
            for m in os.environ.get("OPENROUTER_FALLBACK_MODELS", "").split(",")
            if m.strip()
        ]
        self.memory_max_messages = int(os.environ.get("MEMORY_MAX_MESSAGES", "20"))
        self.system_prompt = os.environ.get(
            "SYSTEM_PROMPT",
            "Voce e um assistente amigavel e direto em um servidor do Discord. "
            "Responda em portugues, de forma natural e concisa.",
        )


config = Config()
