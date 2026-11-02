"""Parity and failure boundaries for the optional, database-free MCP tools."""
import pytest
from pydantic import ValidationError
from astral_nexus_mcp.engines import astrology, bazi
from astral_nexus_mcp.engines.birth_time import CalculationError
from astral_nexus_mcp.tools import BirthInput, calculate_astrology, calculate_bazi

BIRTH = {'birth_date': '2005-12-23', 'local_time': '08:37',
         'timezone': 'Asia/Shanghai', 'location': {'latitude': 31.23, 'longitude': 121.47}}


def test_astrology_matches_existing_engine():
    birth = BirthInput(**BIRTH)
    actual = calculate_astrology(birth)
    expected, _ = astrology.calculate(birth.profile(), {})
    assert actual['result'] == expected
    assert actual['service_id'] == 'astrology'
    assert actual['settings']['house_system'] == 'Placidus'


def test_bazi_reference_and_optional_luck():
    from astral_nexus_mcp.engines.bazi_options import BaziOptions
    birth = BirthInput(**BIRTH, sex='M')
    actual = calculate_bazi(birth, BaziOptions(true_solar_time=False), 2030)
    expected, _ = bazi.calculate(birth.profile(), 'civil')
    assert actual['result']['pillars'] == expected['pillars']
    assert [p['gan_zhi'] for p in actual['result']['pillars']] == ['乙酉', '戊子', '辛巳', '壬辰']
    assert actual['result']['luck']['engine_version']
    assert 'luck' not in calculate_bazi(birth)['result']


@pytest.mark.parametrize('changes', [
    {'local_time': '24:00'}, {'birth_date': 'invalid'},
    {'location': {'latitude': 91, 'longitude': 0}},
    {'location': {'latitude': 0, 'longitude': float('nan')}}, {'profile_id': 'other-user'},
])
def test_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        BirthInput(**(BIRTH | changes))


@pytest.mark.parametrize(('changes', 'code'), [
    ({'timezone': 'invalid'}, 'INVALID_BIRTH_TIME'),
    ({'birth_date': '1799-01-01'}, 'DATE_OUT_OF_RANGE'),
    ({'birth_date': '2024-11-03', 'local_time': '01:30', 'timezone': 'America/New_York'}, 'AMBIGUOUS_LOCAL_TIME'),
    ({'birth_date': '2024-03-10', 'local_time': '02:30', 'timezone': 'America/New_York'}, 'NONEXISTENT_LOCAL_TIME'),
])
def test_time_errors_preserved(changes, code):
    with pytest.raises(CalculationError) as exc:
        calculate_astrology(BirthInput(**(BIRTH | changes)))
    assert exc.value.code == code


def test_luck_requires_sex():
    with pytest.raises(CalculationError) as exc:
        calculate_bazi(BirthInput(**BIRTH), through_year=2030)
    assert exc.value.code == 'SEX_REQUIRED'
