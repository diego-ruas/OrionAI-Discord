"""Formatacao da resposta antes de ir para o Discord.

Duas coisas acontecem aqui: a resposta e cortada num ponto limpo se passar do limite
configurado, e depois e quebrada em mensagens separadas nos paragrafos - varias
mensagens curtas parecem alguem conversando, um bloco unico e longo parece saida de
maquina.
"""

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
            # Nao deixa uma mensagem so com o rodape de corte, nem parte um bloco de
            # codigo que abriu num paragrafo e fecha em outro.
            or paragraph.startswith("-# ")
            or _has_unclosed_code_block(chunks[-1])
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
