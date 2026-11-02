"""First Bazi chart: four pillars, hidden stems and ten-god relationships."""
from importlib.metadata import version
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
import math
import swisseph as swe
from lunar_python import Solar
from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.birth_time import CalculationError, utc_birth
from astral_nexus_mcp.engines.swiss import EPHE_PATH, LOCK
from astral_nexus_mcp.engines.bazi_luck import luck_direction

ENGINE_VERSION = 'bazi-lunar-5'
SETTINGS = {
    'year_boundary': 'Li Chun instant',
    'month_boundary': 'Jie instant',
    'solar_term_clock': 'UTC+08:00 Chinese standard time',
    'day_boundary': '23:00 (late Zi hour belongs to next day)',
    'lunar_python_version': version('lunar_python'),
}


def settings_for(time_basis='apparent_solar', day_boundary='23:00'):
    return {**SETTINGS, 'time_basis': time_basis, 'day_boundary': day_boundary,
            'calculation_options': {'true_solar_time': time_basis == 'apparent_solar', 'day_boundary': day_boundary},
            'day_hour_clock': 'birthplace apparent solar time' if time_basis == 'apparent_solar' else 'birthplace civil time'}


def apparent_solar_clock(instant, longitude):
    if not isinstance(longitude, (int, float)) or not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise CalculationError('INVALID_LOCATION', '档案缺少有效经度')
    if not all((EPHE_PATH / name).exists() for name in ('seas_18.se1', 'sepl_18.se1')):
        raise CalculationError('EPHEMERIS_UNAVAILABLE', '真太阳时星历文件缺失')
    hour = instant.hour + instant.minute / 60 + instant.second / 3600 + instant.microsecond / 3_600_000_000
    with LOCK:
        swe.set_ephe_path(str(EPHE_PATH))
        jd = swe.julday(instant.year, instant.month, instant.day, hour, swe.GREG_CAL)
        try:
            _, flags = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
            if not flags & swe.FLG_SWIEPH:
                raise CalculationError('EPHEMERIS_UNAVAILABLE', '星历文件不可用，已拒绝自动降级计算')
            equation_seconds = swe.time_equ(jd) * 86400
        except swe.Error as exc:
            raise CalculationError('EPHEMERIS_UNAVAILABLE', '均时差计算失败') from exc
    longitude_seconds = longitude * 240
    wall_time = instant + timedelta(seconds=longitude_seconds + equation_seconds)
    return wall_time.replace(tzinfo=None), round(equation_seconds, 3), round(longitude_seconds, 3)


def _chart(moment, day_boundary='23:00'):
    solar = Solar.fromYmdHms(moment.year, moment.month, moment.day,
                             moment.hour, moment.minute, moment.second)
    chart = solar.getLunar().getEightChar()
    chart.setSect(1 if day_boundary == '23:00' else 2)
    return chart


def calculate(profile, time_basis='apparent_solar', day_boundary='23:00'):
    if time_basis not in ('civil', 'apparent_solar'):
        raise CalculationError('INVALID_TIME_BASIS', '请选择有效的时间口径')
    if day_boundary not in ('23:00','00:00'): raise CalculationError('INVALID_DAY_BOUNDARY', '请选择有效换日规则')
    instant = utc_birth(profile)
    local = instant.astimezone(ZoneInfo(profile['timezone']))
    shanghai = instant.astimezone(timezone(timedelta(hours=8)))
    clock = local
    time_details = {'basis': time_basis, 'day_boundary': day_boundary}
    if time_basis == 'apparent_solar':
        longitude = (profile.get('location') or {}).get('longitude')
        clock, equation_seconds, longitude_seconds = apparent_solar_clock(instant, longitude)
        time_details.update(equation_of_time_seconds=equation_seconds,
                            longitude_offset_seconds=longitude_seconds,
                            longitude=longitude)
    try:
        term_chart = _chart(shanghai, day_boundary)
        local_chart = _chart(clock, day_boundary)
        pillars = [term_chart.getYear(), term_chart.getMonth(),
                   local_chart.getDay(), local_chart.getTime()]
        day_master = pillars[2][0]
        rows = []
        for key, label, value in zip(('year', 'month', 'day', 'hour'),
                                     ('年柱', '月柱', '日柱', '时柱'), pillars):
            stem, branch = value[0], value[1]
            hidden = list(LunarUtil.ZHI_HIDE_GAN[branch])
            rows.append({'id': key, 'label': label, 'gan_zhi': value,
                         'stem': stem, 'branch': branch,
                         'stem_ten_god': '日主' if key == 'day' else LunarUtil.SHI_SHEN[day_master + stem],
                         'hidden_stems': [{'stem': h, 'ten_god': LunarUtil.SHI_SHEN[day_master + h]}
                                          for h in hidden]})
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise CalculationError('CALENDAR_UNAVAILABLE', '该出生时间无法完成四柱历法计算') from exc
    result = {'utc': instant.isoformat().replace('+00:00', 'Z'),
              'local_time': local.isoformat(timespec='minutes'),
              'solar_term_time': shanghai.isoformat(timespec='minutes'),
              'day_hour_clock': clock.isoformat(timespec='seconds'),
              'time_details': time_details,
              'day_master': day_master, 'pillars': rows,
              'luck_direction': luck_direction(pillars[0][0], profile['sex']) if profile.get('sex') else None}
    interpretation = {'summary': f"四柱：{' · '.join(pillars)}；日主：{day_master}。",
                      'note': '本报告只列出可核对的四柱、藏干与十神关系；格局、喜用神和运势尚未开发。'}
    return result, interpretation


def calculate_pillars(snapshot, day_boundary='23:00'):
    """Use the explicitly selected calendar occurrence, never invent a physical UTC/location."""
    from datetime import datetime
    from astral_nexus_mcp.engines.ziwei_pillars import candidates
    match = {'birth_date':snapshot['birth_date'],'local_time':snapshot['local_time']}
    if match not in candidates(snapshot['pillars']):
        raise CalculationError('INVALID_PILLARS','请选择与四柱相符的日期')
    # The fixed +08 clock is a calendrical coordinate for solar terms only.
    # It does not assert an actual birthplace, time zone or UTC birth instant.
    moment = datetime.fromisoformat(snapshot['birth_date']+'T'+snapshot['local_time'])
    result, interpretation = calculate({'birth_date':snapshot['birth_date'], 'local_time':snapshot['local_time'],
        'timezone':'Asia/Shanghai','time_precision':'exact','sex':snapshot['sex']},'civil',day_boundary)
    if [p['gan_zhi'] for p in result['pillars']] != [snapshot['pillars'][k] for k in ('year','month','day','hour')]:
        raise CalculationError('INVALID_PILLARS','四柱与所选日期不一致')
    result.update(utc=None, local_time=moment.isoformat(timespec='minutes'), solar_term_time=moment.isoformat(timespec='minutes'))
    result['time_details'].update(source='pillars', precision='pillar_representative', timezone=None)
    return result, interpretation
