from datetime import datetime, timedelta

import pytest

from app.utils import clock

TZ = "America/Sao_Paulo"


def _agora():
    return datetime.now(clock._resolve_zone(TZ))


def test_resolve_zone_cai_para_utc_em_nome_invalido():
    zona = clock._resolve_zone("Nao/Existe")
    assert datetime.now(zona).utcoffset() == timedelta(0)


def test_resolve_zone_sem_nome_usa_utc():
    assert datetime.now(clock._resolve_zone("")).utcoffset() == timedelta(0)


def test_resolve_zone_valida_nao_e_utc():
    # Se o tzdata nao estiver instalado isto falha - e e exatamente o que queremos saber,
    # porque sem ele o bot inteiro passa a operar em UTC (ver requirements.txt).
    zona = clock._resolve_zone(TZ)
    assert datetime.now(zona).utcoffset() != timedelta(0)


@pytest.mark.parametrize(
    "hora,esperado",
    [
        (0, "madrugada"), (4, "madrugada"),
        (5, "manha"), (11, "manha"),
        (12, "tarde"), (17, "tarde"),
        (18, "noite"), (23, "noite"),
    ],
)
def test_period_of_day(hora, esperado):
    assert clock.period_of_day(hora) == esperado


def test_now_description_traz_data_hora_e_periodo():
    agora = _agora()
    texto = clock.now_description(TZ)
    assert clock.WEEKDAYS[agora.weekday()] in texto
    assert clock.MONTHS[agora.month - 1] in texto
    assert str(agora.year) in texto
    assert clock.period_of_day(agora.hour) in texto
