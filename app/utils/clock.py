"""Data/hora local, para o bot saber quando a conversa acontece.

Sem isso o modelo nao tem nocao de "hoje", "agora", "de manha" - e responder
"bom dia" as duas da manha e uma das coisas que mais denunciam um bot.
"""

from datetime import datetime, timezone

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
