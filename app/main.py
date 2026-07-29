import asyncio
import re

import discord

from .config import PERSONA_PRESETS, config
from .db import add_message, clear_history, get_history, get_persona, set_persona
from .openrouter import generate_reply

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.dm_messages = True

client = discord.Client(
    intents=intents,
    # So permite marcar usuarios especificos; bloqueia @everyone/@here/cargos mesmo
    # que o modelo tente gerar isso (defesa contra jailbreak/injecao gerando spam de ping).
    allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=False),
)

# Evita respostas simultaneas concorrentes para o mesmo usuario (protege a memoria/historico).
_locks_by_user = {}


async def with_user_lock(user_id, fn):
    lock = _locks_by_user.setdefault(user_id, asyncio.Lock())
    async with lock:
        return await fn()


def should_respond(message):
    if message.author.bot:
        return False
    if isinstance(message.channel, discord.DMChannel):
        return True
    return client.user in message.mentions


def strip_mention(content):
    pattern = re.compile(rf"<@!?{client.user.id}>")
    return pattern.sub("", content).strip()


def truncate_reply(text, max_chars):
    text = text.strip()
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    # Corta no ultimo fim de paragrafo/frase antes do limite, pra nao truncar no
    # meio de uma palavra ou frase quando o modelo ignorar a instrucao de ser breve.
    best_break = max(
        cut.rfind("\n\n"),
        cut.rfind(". "),
        cut.rfind("! "),
        cut.rfind("? "),
        cut.rfind("\n"),
    )
    if best_break > max_chars * 0.5:
        cut = cut[: best_break + 1]

    return cut.rstrip() + "\n-# (resposta cortada por ser muito longa)"


async def handle_mode_command(message, channel_id, text):
    parts = text.split(maxsplit=1)
    requested = parts[1].strip().lower() if len(parts) > 1 else ""

    if not requested:
        current = get_persona(channel_id) or "padrao"
        options = ", ".join(PERSONA_PRESETS.keys())
        await message.reply(
            f"Modo atual: **{current}**. Opcoes disponiveis: {options}. "
            f"Use `!modo <nome>` para trocar."
        )
        return

    if requested not in PERSONA_PRESETS:
        options = ", ".join(PERSONA_PRESETS.keys())
        await message.reply(f"Modo '{requested}' nao existe. Opcoes: {options}.")
        return

    set_persona(channel_id, requested)
    await message.reply(f"Modo alterado para **{requested}**.")


@client.event
async def on_ready():
    print(f"Bot conectado como {client.user}")


@client.event
async def on_message(message):
    if not should_respond(message):
        return

    user_id = message.author.id
    text = strip_mention(message.content)
    channel_id = str(message.channel.id)

    if text == "!reset":
        clear_history(channel_id)
        await message.reply("Memoria apagada. Podemos comecar do zero.")
        return

    if text.lower().startswith("!modo"):
        await handle_mode_command(message, channel_id, text)
        return

    if not text:
        return

    async def handle():
        async with message.channel.typing():
            history = get_history(channel_id, config.memory_max_messages)

            # Formata historico com nome + id do usuario (para o modelo poder marcar
            # alguem usando <@id> quando fizer sentido) se houver multiplos usuarios
            formatted_history = []
            for h in history:
                if h["role"] == "user" and h["username"] and h["username"] != "Unknown":
                    formatted_history.append(
                        {
                            "role": h["role"],
                            "content": f"**{h['username']}** (id: {h['user_id']}): {h['content']}",
                        }
                    )
                else:
                    formatted_history.append({"role": h["role"], "content": h["content"]})

            current_content = f"**{message.author.name}** (id: {user_id}): {text}"

            # Usuarios que o Discord ja resolveu de verdade (o autor usou @ de fato),
            # para o modelo ter ids confiaveis em vez de adivinhar a partir de nomes soltos.
            mentioned_users = [m for m in message.mentions if m.id != client.user.id]
            if mentioned_users:
                mentions_list = ", ".join(f"**{m.name}** (id: {m.id})" for m in mentioned_users)
                current_content += f"\n(usuarios mencionados de verdade nesta mensagem: {mentions_list})"

            persona_key = get_persona(channel_id) or "padrao"
            system_prompt = config.build_system_prompt(persona_key)

            messages = [
                {"role": "system", "content": system_prompt},
                *formatted_history,
                {"role": "user", "content": current_content},
            ]

            try:
                reply = await generate_reply(messages)
                reply = truncate_reply(reply, config.max_reply_chars)[:2000]
                add_message(
                    channel_id, str(user_id), message.author.name, "user", text, config.memory_max_messages
                )
                add_message(
                    channel_id,
                    str(client.user.id),
                    client.user.name,
                    "assistant",
                    reply,
                    config.memory_max_messages,
                )
                await message.reply(reply)
            except Exception as err:  # noqa: BLE001 - mirrors JS catch-all
                print(f"[bot] Erro ao gerar resposta: {err}")
                await message.reply(
                    "Desculpa, tive um problema para responder agora (provavelmente limite de "
                    "uso dos modelos gratuitos). Tenta de novo em instantes."
                )

    await with_user_lock(user_id, handle)


def main():
    client.run(config.discord_token)


if __name__ == "__main__":
    main()
