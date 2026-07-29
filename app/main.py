import asyncio
import re

import discord

from .config import config
from .db import add_message, clear_history, get_history
from .openrouter import generate_reply

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.dm_messages = True

client = discord.Client(intents=intents)

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

    if not text:
        return

    async def handle():
        async with message.channel.typing():
            history = get_history(channel_id, config.memory_max_messages)

            # Formata historico com nome do usuario se houver multiplos usuarios
            formatted_history = []
            for h in history:
                if h["role"] == "user" and h["username"] and h["username"] != "Unknown":
                    formatted_history.append(
                        {"role": h["role"], "content": f"**{h['username']}**: {h['content']}"}
                    )
                else:
                    formatted_history.append({"role": h["role"], "content": h["content"]})

            messages = [
                {"role": "system", "content": config.system_prompt},
                *formatted_history,
                {"role": "user", "content": f"**{message.author.name}**: {text}"},
            ]

            try:
                reply = await generate_reply(messages)
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
                await message.reply(reply[:2000])
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
