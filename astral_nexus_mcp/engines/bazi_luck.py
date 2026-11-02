"""Deterministic luck cycles from an owned, versioned Bazi chart report."""
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from lunar_python import Solar
from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.birth_time import CalculationError
from astral_nexus_mcp.engines.bazi_luck_interactions import review as review_interactions

ENGINE_VERSION = 'bazi-luck-4'
STANDARD_TIME = timezone(timedelta(hours=8))
SETTINGS = {
    'solar_term_clock': 'UTC+08:00 Chinese standard time',
    'start_conversion': '3 days/year, 6 hours/month, 12 minutes/day, 30 seconds/hour; selected birth clock truncated to minute; whole-hour result',
    'start_clock': 'selected Bazi report apparent solar clock when requested, otherwise UTC+08:00 standard clock',
    'term_clock': 'UTC+08:00 standard clock even when selected birth clock is apparent solar',
    'start_date_basis': 'actual birth instant in UTC+08:00 plus calendar offset',
    'period_count': 8,
    'annual_boundary': 'Li Chun instant',
    'lunar_python_version': version('lunar_python'),
}
YANG_STEMS = frozenset('甲丙戊庚壬')
YIN_STEMS = frozenset('乙丁己辛癸')


def luck_direction(year_stem: str, sex: str) -> str:
    """阳男阴女顺排；阴男阳女逆排，using the Li Chun year stem."""
    if year_stem not in YANG_STEMS | YIN_STEMS:
        raise CalculationError('INVALID_YEAR_STEM', '年干无法用于判定大运顺逆')
    if sex not in ('M', 'F'):
        raise CalculationError('SEX_REQUIRED', '请先在出生档案中选择排运所用性别')
    is_yang = year_stem in YANG_STEMS
    return 'forward' if is_yang == (sex == 'M') else 'reverse'


def _datetime(solar):
    return datetime.strptime(solar.toYmdHms(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=STANDARD_TIME)


def _li_chun(year):
    return _datetime(Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()['立春'])


def _offset_from_term(seconds):
    """The old 3-day/1-year rule decomposed without float or 365/30-day dates."""
    whole = int(seconds)
    years, whole = divmod(whole, 3 * 86400)
    months, whole = divmod(whole, 6 * 3600)
    days, whole = divmod(whole, 12 * 60)
    hours, _ = divmod(whole, 30)
    return {'years': years, 'months': months, 'days': days, 'hours': hours}


def calculate(chart_snapshot: dict, chart_result: dict, through_year: int):
    """Return time facts only; no auspice score, pattern, or favorable element."""
    sex = chart_snapshot.get('sex')
    if sex not in ('M', 'F'):
        raise CalculationError('SEX_REQUIRED', '请先在出生档案中填写排运所用性别，并重新生成八字报告')
    if not 1800 <= through_year <= 2399:
        raise CalculationError('INVALID_YEAR_RANGE', '流年截止年份超出排盘范围')
    try:
        born = (datetime.fromisoformat(chart_result['day_hour_clock']).replace(tzinfo=STANDARD_TIME)
                if (chart_result.get('time_details') or {}).get('source') == 'pillars'
                else datetime.fromisoformat(chart_result['utc'].replace('Z', '+00:00')))
        standard = born.astimezone(STANDARD_TIME)
        lunar = Solar.fromYmdHms(standard.year, standard.month, standard.day,
                                 standard.hour, standard.minute, standard.second).getLunar()
        eight = lunar.getEightChar()
        eight.setSect(1)
        year_pillar, month_pillar = [p['gan_zhi'] for p in chart_result['pillars'][:2]]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise CalculationError('INVALID_CHART_REPORT', '八字报告缺少可核对的出生信息') from exc
    if (eight.getYear(), eight.getMonth()) != (year_pillar, month_pillar):
        raise CalculationError('CHART_RULE_MISMATCH', '八字报告的节气口径与大运计算不一致，请重新生成八字报告')
    direction = luck_direction(year_pillar[0], sex)
    reference = lunar.getNextJie() if direction == 'forward' else lunar.getPrevJie()
    reference_time = _datetime(reference.getSolar())
    basis = (chart_result.get('time_details') or {}).get('basis')
    if basis == 'apparent_solar':
        try:
            birth_clock = datetime.fromisoformat(chart_result['day_hour_clock']).replace(
                second=0, microsecond=0, tzinfo=STANDARD_TIME)
        except (KeyError, TypeError, ValueError) as exc:
            raise CalculationError('INVALID_CHART_REPORT', '八字报告缺少真太阳时时钟') from exc
    elif basis == 'civil':
        birth_clock = standard.replace(second=0, microsecond=0)
    else:
        raise CalculationError('INVALID_CHART_REPORT', '八字报告缺少明确的日时柱时间口径')
    difference = (reference_time - birth_clock) if direction == 'forward' else (birth_clock - reference_time)
    if difference.total_seconds() < 0:
        raise CalculationError('CALENDAR_UNAVAILABLE', '所选时钟跨越节气交接，无法按当前口径计算起运')
    offset = _offset_from_term(difference.total_seconds())
    birth_solar = Solar.fromYmdHms(standard.year, standard.month, standard.day,
                                   standard.hour, standard.minute, standard.second)
    start_solar = birth_solar.nextYear(offset['years']).nextMonth(offset['months']).next(
        offset['days']).nextHour(offset['hours'])
    start = _datetime(start_solar)
    periods = []
    month_index = LunarUtil.getJiaZiIndex(month_pillar)
    if month_index < 0:
        raise CalculationError('CHART_RULE_MISMATCH', '月柱不在六十甲子序列中')
    for index in range(8):
        period_start = _datetime(start_solar.nextYear(index * 10))
        period_end = _datetime(start_solar.nextYear((index + 1) * 10))
        offset_index = index + 1 if direction == 'forward' else -index - 1
        gan_zhi = LunarUtil.JIA_ZI[(month_index + offset_index) % 60]
        periods.append({'number': index + 1, 'gan_zhi': gan_zhi,
                        'start': period_start.isoformat(), 'end_exclusive': period_end.isoformat()})
    first_annual_year = standard.year if standard >= _li_chun(standard.year) else standard.year - 1
    if through_year < first_annual_year:
        raise CalculationError('INVALID_YEAR_RANGE', '流年截止年份早于出生所属节气年')
    annual = []
    for year in range(first_annual_year, through_year + 1):
        annual_start, annual_end = _li_chun(year), _li_chun(year + 1)
        overlapping = [p['number'] for p in periods
                       if datetime.fromisoformat(p['start']) < annual_end
                       and datetime.fromisoformat(p['end_exclusive']) > annual_start]
        annual.append({'year': year, 'gan_zhi': LunarUtil.JIA_ZI[(year - 1984) % 60],
                       'start': annual_start.isoformat(), 'end_exclusive': annual_end.isoformat(),
                       'overlapping_periods': overlapping})
    result = {'chart_utc': chart_result['utc'], 'birth_standard_time': standard.isoformat(),
              'birth_clock_for_start': birth_clock.replace(tzinfo=None).isoformat(), 'birth_clock_basis': basis,
              'direction': direction,
              'reference_term': {'name': reference.getName(), 'time': reference_time.isoformat(),
                                 'elapsed_minutes': int(difference.total_seconds() // 60)},
              'start_offset': offset,
              'start_time': start.isoformat(), 'periods': periods, 'annual': annual}
    if (chart_result.get('time_details') or {}).get('source') == 'pillars':
        result['time_precision'] = 'pillar_representative'
        result['precision_notice'] = '四柱候选时刻仅为时柱代表值；起运时间与跨运分界为代表值，不是精确出生时刻。'
    result['interaction_review'] = review_interactions(chart_result, result)
    interpretation = {'summary': f"大运{'顺排' if direction == 'forward' else '逆排'}，于 {start.isoformat()}（东八区标准时）起运。",
                      'note': '列出节气、起运、旧大运关系谓词及每条条件格局路径的岁运透干方向；流年关系无旧成立谓词，均保留未判定。没有年度吉凶分或作用后余额，不自动判定最终格局和喜用神。'}
    return result, interpretation
