"""Data/hora local, para o bot saber quando a conversa acontece e agendar lembretes.

Sem isso o modelo nao tem nocao de "hoje", "agora", "de manha" - e responder
"bom dia" as duas da manha e uma das coisas que mais denunciam um bot. Aqui tambem
mora a interpretacao de horarios ("amanha as 9") usada pelos lembretes.
"""

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

WEEKDAYS = [
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
]

MONTHS = [
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _resolve_zone(tz_name):
    if not tz_name or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - tzdata ausente ou nome invalido
        print(f"[clock] Timezone '{tz_name}' indisponivel, usando UTC.")
        return timezone.utc


def period_of_day(hour):
    if 5 <= hour < 12:
        return "manha"
    if 12 <= hour < 18:
        return "tarde"
    if 18 <= hour < 24:
        return "noite"
    return "madrugada"


def now_description(tz_name):
    now = datetime.now(_resolve_zone(tz_name))
    return (
        f"{WEEKDAYS[now.weekday()]}, {now.day} de {MONTHS[now.month - 1]} de "
        f"{now.year}, {now:%H:%M} ({period_of_day(now.hour)})"
    )


def now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# Formatos aceitos no campo "at" do agendamento de lembretes, do mais completo ao
# mais curto. So horario ("14:30") vale para hoje - quem resolve se e hoje ou amanha
# e parse_local_datetime, comparando com o agora.
_AT_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M", "%H:%M")


def parse_local_datetime(text, tz_name):
    """Interpreta uma data/hora local escrita pelo modelo e devolve epoch em ms.

    Levanta ValueError se nao der para entender. Horario sem data cai no proximo
    horario correspondente (hoje se ainda nao passou, senao amanha), que e o que
    alguem quer dizer com "me lembra as 9".
    """
    text = (text or "").strip().replace("  ", " ")
    if not text:
        raise ValueError("horario vazio")

    zone = _resolve_zone(tz_name)
    now = datetime.now(zone)

    for fmt in _AT_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue

        # Formatos sem ano/data usam o dia de hoje como base.
        if "%Y" not in fmt:
            parsed = parsed.replace(year=now.year)
            if "%d" not in fmt:
                parsed = parsed.replace(month=now.month, day=now.day)

        local = parsed.replace(tzinfo=zone)

        # "as 9" quando ja passou das 9 significa amanha as 9.
        if local <= now and "%d" not in fmt:
            local = local + timedelta(days=1)

        return int(local.timestamp() * 1000)

    raise ValueError(f"nao entendi o horario '{text}'")


def describe_timestamp(ms, tz_name):
    """Formata um instante salvo no banco para mostrar ao usuario."""
    local = datetime.fromtimestamp(ms / 1000, _resolve_zone(tz_name))
    today = datetime.now(_resolve_zone(tz_name)).date()
    delta_days = (local.date() - today).days

    if delta_days == 0:
        return f"hoje as {local:%H:%M}"
    if delta_days == 1:
        return f"amanha as {local:%H:%M}"
    return (
        f"{WEEKDAYS[local.weekday()]}, {local.day} de {MONTHS[local.month - 1]} "
        f"as {local:%H:%M}"
    )
