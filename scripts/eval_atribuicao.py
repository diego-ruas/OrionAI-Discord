"""Mede, contra o modelo real, quantas vezes o bot atribui algo a pessoa errada.

Ferramenta manual (usa rede e gasta cota do OpenRouter), fora do pytest.

    .venv\\Scripts\\python scripts\\eval_atribuicao.py [--n 5] [--seed 1] \\
        [--kinds historico,ambiente,fatos,curadoria] [--delay 3]

Nao importa app.db nem app.main: assim nao cria banco nem sobe cliente Discord.
"""

import argparse
import asyncio
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config  # noqa: E402
from app.openrouter import RateLimitError, generate_reply  # noqa: E402
from app.utils.chat_format import (  # noqa: E402
    compose_context,
    format_history,
    format_user_line,
    speaker_label,
)
from app.utils.clock import local_hhmm  # noqa: E402
from app.utils.http_client import close_session  # noqa: E402
from app.utils.memory_format import (  # noqa: E402
    build_curator_messages,
    parse_curator_reply,
    resolve_author,
    resolve_subject,
)

# Nomes parecidos de proposito: Ana/Anna, Joao/Joana, Lucas/Luca, Mari/Mario.
PEOPLE = [
    ("Ana", "ana_b", 1001),
    ("Anna", "anna.s", 1002),
    ("Joao", "joaozin", 1003),
    ("Joana", "jo_ana", 1004),
    ("Lucas", "lucas_m", 1005),
    ("Luca", "luca99", 1006),
    ("Mari", "mari_c", 1007),
    ("Mario", "mariobros", 1008),
]

# (palavra, primeira pessoa, terceira pessoa, pergunta)
FACTS = [
    ("gato", "eu tenho um gato chamado Pipoca", "tem um gato chamado Pipoca", "quem aqui tem gato?"),
    ("Curitiba", "eu moro em Curitiba", "mora em Curitiba", "quem aqui mora em Curitiba?"),
    ("violao", "eu toco violao", "toca violao", "quem aqui toca violao?"),
    ("Rust", "eu programo em Rust", "programa em Rust", "quem aqui programa em Rust?"),
    ("vegetariano", "eu sou vegetariano", "e vegetariano", "quem aqui e vegetariano?"),
    ("maratona", "eu vou correr uma maratona", "vai correr uma maratona", "quem aqui vai correr maratona?"),
    ("enfermeira", "eu trabalho de enfermeira", "trabalha de enfermeira", "quem aqui e enfermeira?"),
    ("Fortnite", "eu so jogo Fortnite", "so joga Fortnite", "quem aqui joga Fortnite?"),
]

FILLER = [
    "kkkk",
    "bom dia gente",
    "alguem viu o jogo ontem?",
    "affs",
    "boa noite",
    "eita",
    "verdade kkk",
    "to com sono",
]

PLACE = "Voce esta no canal #geral do servidor 'teste', onde varias pessoas conversam."
BASE_MS = 1_700_000_000_000
KINDS = ["historico", "ambiente", "fatos", "curadoria"]


def make_scenario(rng):
    people = rng.sample(PEOPLE, 4)
    facts = rng.sample(FACTS, 4)
    owners = list(zip(people, facts))
    target_idx = rng.randrange(4)
    asker_idx = rng.choice([i for i in range(4) if i != target_idx])
    return owners, target_idx, asker_idx


def mentions(text, person):
    display, username, _ = person
    pattern = r"\b(" + "|".join(re.escape(x) for x in (display, username)) + r")\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def score_answer(reply, owners, target_idx, asker_idx):
    """Acerto: cita o alvo e nenhuma das outras duas pessoas. O perguntador e excluido
    porque o bot pode chama-lo pelo nome."""
    if not mentions(reply, owners[target_idx][0]):
        return False
    others = [o[0] for i, o in enumerate(owners) if i not in (target_idx, asker_idx)]
    return not any(mentions(reply, p) for p in others)


def filler_lines(rng, people, count):
    return [(rng.choice(people), rng.choice(FILLER)) for _ in range(count)]


def build_user_row(person, text, created_at):
    display, username, user_id = person
    return {
        "role": "user",
        "user_id": str(user_id),
        "username": username,
        "display_name": display,
        "content": text,
        "created_at": created_at,
    }


async def run_chat_kind(kind, rng):
    owners, target_idx, asker_idx = make_scenario(rng)
    people = [o[0] for o in owners]
    fact_lines = [(p, f[1]) for p, f in owners]
    fillers = filler_lines(rng, people, 4)
    facts_block = []
    ambient = []
    entries = []  # (person, text)

    if kind == "historico":
        entries = fact_lines + fillers
    elif kind == "ambiente":
        entries = fillers
    else:
        entries = fillers
        facts_block = [
            {"subject": speaker_label(p[0], p[1]), "fact": f[2]} for p, f in owners
        ]
    rng.shuffle(entries)

    rows = [build_user_row(p, t, BASE_MS + i * 60000) for i, (p, t) in enumerate(entries)]
    if kind == "historico":
        for text in ("haha", "boa"):
            rows.insert(rng.randrange(len(rows) + 1), {"role": "assistant", "content": text})
    if kind == "ambiente":
        ambient = [
            {
                "username": p[1],
                "display_name": p[0],
                "content": t,
                "created_at": BASE_MS + i * 60000,
            }
            for i, (p, t) in enumerate(fact_lines)
        ]
        rng.shuffle(ambient)
        for i, m in enumerate(ambient):
            m["created_at"] = BASE_MS + i * 60000

    asker = owners[asker_idx][0]
    question = FACTS_BY_WORD[owners[target_idx][1][0]][3]
    now_ms = BASE_MS + 10 * 60000
    context = compose_context("teste", PLACE, facts_block, "", ambient, config.timezone)
    messages = [
        {"role": "system", "content": config.build_system_prompt(context)},
        *format_history(rows, config.timezone),
        {
            "role": "user",
            "content": format_user_line(
                speaker_label(asker[0], asker[1]),
                asker[2],
                local_hhmm(now_ms, config.timezone),
                question,
            ),
        },
    ]
    reply = await generate_reply(messages, use_tools=False)
    ok = score_answer(reply or "", owners, target_idx, asker_idx)
    expected = speaker_label(owners[target_idx][0][0], owners[target_idx][0][1])
    return ok, question, expected, reply or ""


async def run_curadoria(rng):
    owners, _, _ = make_scenario(rng)
    people = [o[0] for o in owners]
    entries = [(p, f[1]) for p, f in owners] + filler_lines(rng, people, 4)
    rng.shuffle(entries)
    rows = [build_user_row(p, t, BASE_MS + i * 60000) for i, (p, t) in enumerate(entries)]
    reply = await generate_reply(build_curator_messages("", [], [], rows), use_tools=False)
    parsed = parse_curator_reply(reply)
    if parsed is None:
        return [(False, "curadoria", "JSON valido", reply or "")]
    results = []
    for f in parsed["facts"]:
        owner = None
        for person, fact in owners:
            if re.search(r"\b" + re.escape(fact[0]) + r"\b", f["fact"], re.IGNORECASE):
                owner = person
                break
        label = f"fato: {f['fact']}"
        if owner is None:
            results.append((False, label, "fato conhecido", str(f)))
            continue
        expected = speaker_label(owner[0], owner[1])
        subject = resolve_subject(f["about"], rows)
        author = resolve_author(f["by"], rows)
        ok = subject == expected and author == str(owner[2])
        results.append((ok, label, f"{expected} / {owner[2]}", f"{subject} / {author}"))
    return results


FACTS_BY_WORD = {f[0]: f for f in FACTS}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--kinds", default=",".join(KINDS))
    parser.add_argument("--delay", type=float, default=3)
    args = parser.parse_args()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    rng = random.Random(args.seed)

    stats = {}  # kind -> [acertos, total]
    errors = []
    rate_limited = False

    def record(kind, ok, question, expected, got):
        s = stats.setdefault(kind, [0, 0])
        s[1] += 1
        if ok:
            s[0] += 1
        else:
            errors.append((kind, question, expected, got))

    try:
        for kind in kinds:
            stats.setdefault(kind, [0, 0])
            for _ in range(args.n):
                try:
                    if kind == "curadoria":
                        for ok, question, expected, got in await run_curadoria(rng):
                            record(kind, ok, question, expected, got)
                    else:
                        ok, question, expected, got = await run_chat_kind(kind, rng)
                        record(kind, ok, question, expected, got)
                except RateLimitError:
                    raise
                except Exception as err:  # noqa: BLE001 - cenario com falha conta como erro
                    record(kind, False, "(excecao)", "resposta do modelo", f"{type(err).__name__}: {err}")
                await asyncio.sleep(args.delay)
    except RateLimitError as err:
        rate_limited = True
        print(f"[eval] Rate limit: {err}. Resultado parcial abaixo.")
    finally:
        await close_session()

    total_ok = total = 0
    for kind in kinds:
        ok, n = stats.get(kind, [0, 0])
        total_ok += ok
        total += n
        pct = f"{100 * ok // n}%" if n else "-"
        print(f"{kind}: {ok}/{n} ({pct})")
    for kind, question, expected, got in errors:
        print(f"\nERRO [{kind}] {question}\n  esperado: {expected}\n  resposta: {got[:200]}")
    pct = f"{100 * total_ok // total}%" if total else "-"
    print(f"\ntotal: {total_ok}/{total} ({pct})")
    if rate_limited:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
