import asyncio

from .config import config
from .db import (
    add_fact,
    count_messages,
    fold_into_summary,
    get_channel_memory,
    get_facts,
    get_messages_after,
    get_oldest_messages,
    set_curated_until,
)
from .openrouter import generate_reply
from .utils import jev
from .utils.clock import local_ddmm
from .utils.memory_format import (
    append_summary,
    build_curator_messages,
    parse_curator_reply,
    resolve_author,
    resolve_subject,
)

# Espera o canal sossegar, para uma troca de varias mensagens virar uma chamada so.
# Modelo :free tem limite de requisicoes.
CURATE_DELAY_SECONDS = 45
# So resume quando sobram ao menos 10 mensagens alem da janela, para nao gastar
# chamada a cada mensagem.
SUMMARY_MIN_BATCH = 10
# Teto de mensagens guardadas alem da janela. Se a curadoria falhar sempre, o banco
# nao cresce sem limite.
HISTORY_SAFETY_MARGIN = 60
# Teto de mensagens novas por chamada.
MAX_NEW_MESSAGES = 60


async def curate_channel(channel_id):
    state = get_channel_memory(channel_id)
    new_rows = get_messages_after(channel_id, state["curated_until"], MAX_NEW_MESSAGES)
    overflow = count_messages(channel_id) - config.memory_max_messages
    fold_rows = get_oldest_messages(channel_id, overflow) if overflow >= SUMMARY_MIN_BATCH else []
    if not new_rows and not fold_rows:
        return

    # Temperatura 0: modelo free criativo na curadoria inventava fato e resumo.
    reply = await generate_reply(
        build_curator_messages(get_facts(channel_id), fold_rows, new_rows),
        use_tools=False,
        temperature=0,
    )
    parsed = parse_curator_reply(reply)
    if parsed is None:
        print(f"[memoria] Resposta invalida da curadoria em {channel_id}: {reply[:200]!r}")
        return

    facts = parsed["facts"]
    if facts:
        # Falha fechada: sem a confirmacao do Jev, nada vira memoria.
        try:
            data = await jev.decide(
                config.openrouter_api_key,
                config.jev_model,
                jev.fact_check_state(new_rows, facts),
                jev.fact_questions(len(facts)),
            )
            confirmed = jev.supported_facts(data, facts)
        except Exception as err:  # noqa: BLE001
            print(f"[memoria] Jev nao conferiu os fatos de {channel_id}, descartando: {err}")
            confirmed = []
        if len(confirmed) < len(facts):
            print(
                f"[memoria] {channel_id}: {len(facts) - len(confirmed)} fato(s) sem respaldo "
                "descartado(s)."
            )
        facts = confirmed

    # Um o!reset durante as chamadas (modelo e Jev) apagou as mensagens: gravar agora
    # ressuscitaria resumo e fatos de conversa que a pessoa mandou apagar. Tem que vir
    # depois de todo await.
    first_id = (fold_rows or new_rows)[0]["id"]
    still_there = get_messages_after(channel_id, first_id - 1, 1)
    if not still_there or still_there[0]["id"] != first_id:
        return

    saved = 0
    rejected = False
    for f in facts:
        author_id = resolve_author(f["by"], new_rows)
        if author_id is None:
            rejected = True
            continue
        if add_fact(
            channel_id,
            f["about"],
            f["fact"],
            config.max_facts_per_channel,
            author_id=author_id,
            max_per_author=config.max_facts_per_author,
        ):
            saved += 1
        else:
            rejected = True
    if rejected and len(get_facts(channel_id)) >= config.max_facts_per_channel:
        print(f"[memoria] Memoria de {channel_id} cheia; fato novo descartado.")

    folded = False
    if fold_rows and parsed["summary"]:
        ts = fold_rows[-1].get("created_at")
        label = local_ddmm(ts, config.timezone) if ts is not None else ""
        fold_into_summary(
            channel_id,
            append_summary(state["summary"], parsed["summary"], label),
            fold_rows[-1]["id"],
        )
        folded = True
    if new_rows:
        set_curated_until(channel_id, new_rows[-1]["id"])

    print(
        f"[memoria] {channel_id}: {saved} fato(s), "
        f"{len(fold_rows) if folded else 0} mensagem(ns) resumida(s)."
    )


_scheduled = {}  # channel_id -> task ainda dormindo
_tasks = set()  # referencia forte: task sem referencia pode ser coletada
_locks = {}  # channel_id -> asyncio.Lock; um por canal, conjunto finito


def schedule_curation(channel_id):
    pending = _scheduled.pop(channel_id, None)
    if pending:
        pending.cancel()
    task = asyncio.create_task(_curate_later(channel_id))
    _scheduled[channel_id] = task
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _curate_later(channel_id):
    await asyncio.sleep(CURATE_DELAY_SECONDS)
    # A task sai de _scheduled antes de chamar o modelo: o cancelamento so atinge
    # task ainda dormindo, entao nenhuma requisicao em andamento e desperdicada.
    if _scheduled.get(channel_id) is asyncio.current_task():
        _scheduled.pop(channel_id, None)
    # Lock por canal: impede duas curadorias lendo o mesmo curated_until. Tasks
    # pendentes no desligamento sao canceladas; curated_until nao avancou, entao a
    # proxima conversa reprocessa essas mensagens.
    async with _locks.setdefault(channel_id, asyncio.Lock()):
        try:
            await curate_channel(channel_id)
        except Exception as err:  # noqa: BLE001 - curadoria nunca derruba o bot
            print(f"[memoria] Curadoria de {channel_id} falhou: {type(err).__name__}: {err}")
