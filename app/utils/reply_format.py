"""Formatacao da resposta antes de ir para o Discord.

Duas coisas acontecem aqui: a resposta e cortada num ponto limpo se passar do limite
configurado, e depois e quebrada em mensagens separadas nos paragrafos - varias
mensagens curtas parecem alguem conversando, um bloco unico e longo parece saida de
maquina.
"""

import difflib
import re
import unicodedata

DISCORD_LIMIT = 2000

# Abaixo disso nao vale quebrar: e uma resposta curta, mandar em pedacos soaria picado.
MIN_CHARS_TO_SPLIT = 220

TRUNCATION_NOTE = "\n-# (resposta cortada por ser muito longa)"


def truncate_reply(text, max_chars):
    text = (text or "").strip()
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

    # Corte no meio de um bloco de codigo deixaria o Discord renderizando o resto da
    # mensagem (inclusive a nota) como codigo.
    if _has_unclosed_code_block(cut):
        cut = cut.rstrip() + "\n```"
    return cut.rstrip() + TRUNCATION_NOTE


def _has_unclosed_code_block(text):
    return text.count("```") % 2 != 0


def _hard_wrap(chunk):
    """Ultimo recurso: parte um bloco maior que o limite do Discord."""
    parts = []
    remaining = chunk
    while len(remaining) > DISCORD_LIMIT:
        cut = remaining[:DISCORD_LIMIT]
        at = max(cut.rfind("\n"), cut.rfind(" "))
        if at < DISCORD_LIMIT * 0.5:
            at = DISCORD_LIMIT
        parts.append(remaining[:at].rstrip())
        remaining = remaining[at:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def split_reply(text, max_messages=3, enabled=True):
    """Quebra a resposta em mensagens separadas nos paragrafos.

    Blocos de codigo nunca sao partidos: se o texto tem ``` , ele sai inteiro
    (respeitando so o limite tecnico do Discord).
    """
    text = (text or "").strip()
    if not text:
        return []

    if not enabled or max_messages <= 1 or len(text) < MIN_CHARS_TO_SPLIT or "```" in text:
        return _hard_wrap(text) if len(text) > DISCORD_LIMIT else [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        return _hard_wrap(text) if len(text) > DISCORD_LIMIT else [text]

    chunks = []
    for paragraph in paragraphs:
        merge = chunks and (
            # Ja usamos todas as mensagens permitidas: o resto vai junto na ultima.
            len(chunks) >= max_messages
            # Nao deixa uma mensagem so com o rodape de corte.
            or paragraph.startswith("-# ")
        )
        if merge:
            chunks[-1] = f"{chunks[-1]}\n\n{paragraph}"
        else:
            chunks.append(paragraph)

    result = []
    for chunk in chunks:
        result.extend(_hard_wrap(chunk) if len(chunk) > DISCORD_LIMIT else [chunk])
    return result


def typing_delay(chunk, chars_per_second, max_seconds):
    """Tempo de 'digitacao' proporcional ao tamanho da mensagem."""
    if chars_per_second <= 0:
        return 0.0
    return min(len(chunk) / chars_per_second, max(max_seconds, 0.0))


def _fold(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


_SPEAKER_LINE = re.compile(r"^\s*\*\*[^*\n]{1,80}\*\*\s*\(id:[^)]*\):\s*")


def strip_speaker_prefix(text, bot_names):
    """Tira do comeco da resposta o rotulo de falante que o modelo copia do historico
    (`**Nome (@x)** (id: 1, 20:00):` ou `Nome:`)."""
    text = _SPEAKER_LINE.sub("", text, count=1)
    for name in bot_names:
        if name:
            text = re.sub(rf"^\s*{re.escape(name)}\s*:\s*", "", text, count=1, flags=re.I)
    return text


_CUSTOM_EMOJI_TOKEN = re.compile(r"<(a?):(\w+):([^>\s]*)>")


def fix_custom_emoji(text, usable_ids):
    """Emoji customizado so vale se o servidor o tem; token inventado ou de outro
    servidor aparece quebrado no Discord, entao vira `:nome:`."""

    def repl(match):
        if match.group(3).isdigit() and match.group(3) in usable_ids:
            return match.group(0)
        return f":{match.group(2)}:"

    return _CUSTOM_EMOJI_TOKEN.sub(repl, text)


_CANNED_CLOSERS = [
    re.compile(p)
    for p in (
        r"(e )?(como|em que) (eu )?posso (te |lhe )?ajudar( agora| hoje| mais)?",
        r"(quer|precisa) (que eu faca |de )?mais alguma coisa",
        r"posso (te )?ajudar (em|com) mais alguma coisa",
        r"(qualquer (coisa|duvida),? )?(e so|so) (chamar|falar|perguntar)",
        r"fico a disposicao",
        r"espero ter ajudado",
    )
]


def strip_canned_closers(text):
    """Remove a frase final de atendimento padrao ("Como posso te ajudar?"), mas nunca
    deixa a resposta vazia."""
    for _ in range(2):
        stripped = text.rstrip()
        sentences = re.split(r"(?<=[.!?…])\s+", stripped)
        if len(sentences) < 2:
            break
        last = sentences[-1]
        folded = re.sub(r"^\W+|\W+$", "", _fold(last))
        if not any(p.fullmatch(folded) for p in _CANNED_CLOSERS):
            break
        text = stripped[: -len(last)].rstrip()
    return text


def _normalize_for_repeat(text):
    text = re.sub(r"<@!?\d+>", "", _fold(text))
    return " ".join(re.sub(r"[^\w\s]", "", text).split())


def is_repetition(reply, previous):
    """Resposta quase igual a uma das anteriores do bot. Curtas nao contam: "kkk" e "ok"
    repetem naturalmente."""
    a = _normalize_for_repeat(reply)
    if len(a) < 15:
        return False
    for old in previous:
        b = _normalize_for_repeat(old)
        if b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
            return True
    return False


def recent_openings(previous, count=3, words=6):
    """Primeiras palavras das ultimas respostas do bot, para pedir outra abertura."""
    openings = []
    for old in previous:
        cleaned = " ".join(re.sub(r"<@!?\d+>", "", old or "").split()[:words])
        if cleaned:
            openings.append(cleaned)
    return openings[-count:]
