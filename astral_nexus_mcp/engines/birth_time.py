"""Resolve an exact birthplace civil time to one unambiguous UTC instant."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CalculationError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def utc_birth(profile):
    if profile['time_precision'] != 'exact' or not profile['local_time']:
        raise CalculationError('EXACT_TIME_REQUIRED', '排盘需要准确出生时间，请先更新档案')
    try:
        day = date.fromisoformat(profile['birth_date']) if isinstance(profile['birth_date'], str) else profile['birth_date']
    except ValueError:
        raise CalculationError('INVALID_BIRTH_TIME', '出生日期无效')
    if not 1800 <= day.year <= 2399:
        raise CalculationError('DATE_OUT_OF_RANGE', '当前计算支持 1800 至 2399 年出生日期')
    try:
        hour, minute = map(int, profile['local_time'].split(':'))
        naive = datetime(day.year, day.month, day.day, hour, minute)
        zone = ZoneInfo(profile['timezone'])
    except (ValueError, KeyError, ZoneInfoNotFoundError):
        raise CalculationError('INVALID_BIRTH_TIME', '出生时间或时区无效')
    candidates = set()
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        instant = local.astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(instant)
    if not candidates:
        raise CalculationError('NONEXISTENT_LOCAL_TIME', '所选时间处于夏令时跳时区间，请修正出生时间')
    if len(candidates) > 1:
        raise CalculationError('AMBIGUOUS_LOCAL_TIME', '所选时间在夏令时回拨时出现两次，请确认准确时刻与时区')
    return candidates.pop()
