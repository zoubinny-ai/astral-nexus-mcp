"""Deterministic tropical natal chart. All Swiss Ephemeris calls share one lock."""
import math
import swisseph as swe
from astral_nexus_mcp.engines.birth_time import CalculationError, utc_birth
from astral_nexus_mcp.engines.swiss import EPHE_PATH, LOCK

ENGINE_VERSION = 'natal-swe-1'
SETTINGS = {'zodiac': 'tropical', 'house_system': 'Placidus', 'ephemeris': 'Swiss Ephemeris',
            'aspect_orbs_degrees': {'conjunction': 8, 'opposition': 8, 'trine': 7, 'square': 6, 'sextile': 5}}
SIGNS = ['白羊座', '金牛座', '双子座', '巨蟹座', '狮子座', '处女座', '天秤座', '天蝎座', '射手座', '摩羯座', '水瓶座', '双鱼座']
PLANETS = [('sun', swe.SUN, '太阳'), ('moon', swe.MOON, '月亮'),
           ('mercury', swe.MERCURY, '水星'), ('venus', swe.VENUS, '金星'),
           ('mars', swe.MARS, '火星'), ('jupiter', swe.JUPITER, '木星'),
           ('saturn', swe.SATURN, '土星'), ('uranus', swe.URANUS, '天王星'),
           ('neptune', swe.NEPTUNE, '海王星'), ('pluto', swe.PLUTO, '冥王星')]
ASPECTS = [('conjunction', 0), ('opposition', 180), ('trine', 120), ('square', 90), ('sextile', 60)]

def _house(longitude, cusps):
    for i in range(12):
        start = cusps[i] % 360
        span = (cusps[(i + 1) % 12] - start) % 360
        if (longitude - start) % 360 < span:
            return i + 1
    raise CalculationError('HOUSE_CALCULATION_FAILED', '无法判定行星宫位')

def calculate(profile, options=None):
    from astral_nexus_mcp.engines.astrology_options import AstrologyOptions, HOUSES, REFERENCE_ORBS
    selected = AstrologyOptions.model_validate(options or {})
    instant = utc_birth(profile)
    if options is not None and not 1800 <= instant.year <= 2399:
        raise CalculationError('UNSUPPORTED_YEAR', '占星设置支持 1800–2399 年')
    location = profile['location']
    lat, lon = location.get('latitude'), location.get('longitude')
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise CalculationError('INVALID_LOCATION', '档案缺少有效经纬度')
    if not all((EPHE_PATH / name).exists() for name in ('seas_18.se1', 'semo_18.se1', 'sepl_18.se1')):
        raise CalculationError('EPHEMERIS_UNAVAILABLE', '星历文件缺失')
    hour = instant.hour + instant.minute / 60 + instant.second / 3600
    with LOCK:
        swe.set_ephe_path(str(EPHE_PATH))
        jd = swe.julday(instant.year, instant.month, instant.day, hour, swe.GREG_CAL)
        try:
            cusps, angles = swe.houses(jd, lat, lon, selected.house_system.encode())
        except swe.Error:
            raise CalculationError('HOUSE_CALCULATION_FAILED', f'该纬度无法使用 {HOUSES[selected.house_system]} 宫制计算')
        planets = []
        for key, body, name in PLANETS:
            try:
                values, flags = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)
            except swe.Error:
                raise CalculationError('EPHEMERIS_UNAVAILABLE', '星历计算失败')
            if not flags & swe.FLG_SWIEPH:
                raise CalculationError('EPHEMERIS_UNAVAILABLE', '星历文件不可用，已拒绝自动降级计算')
            degree = values[0] % 360
            planets.append({'id': key, 'name': name, 'longitude': round(degree, 6),
                            'sign': SIGNS[int(degree // 30)], 'degree_in_sign': round(degree % 30, 4),
                            'house': _house(degree, cusps), 'retrograde': values[3] < 0})
    aspects = []
    for i, first in enumerate(planets):
        for second in planets[i + 1:]:
            separation = abs((first['longitude'] - second['longitude'] + 180) % 360 - 180)
            for aspect, angle in ASPECTS:
                orb = abs(separation - angle)
                if orb <= (REFERENCE_ORBS if options is not None else SETTINGS['aspect_orbs_degrees'])[aspect] * selected.orb_scale:
                    aspects.append({'first': first['id'], 'second': second['id'], 'type': aspect, 'orb': round(orb, 4)})
                    break
    result = {'utc': instant.isoformat().replace('+00:00', 'Z'), 'julian_day_ut': round(jd, 8),
              'planets': planets, 'houses': [{'number': i + 1, 'longitude': round(cusps[i] % 360, 6)} for i in range(12)],
              'angles': {'ascendant': round(angles[0] % 360, 6), 'midheaven': round(angles[1] % 360, 6)},
              'aspects': aspects}
    if options is not None:
        result['calculation_options'] = selected.model_dump()
    interpretation = {'summary': f"太阳位于{planets[0]['sign']}，月亮位于{planets[1]['sign']}。",
                      'note': '以下为象征性星盘信息，并非对人生轨迹的确定性预测。'}
    return result, interpretation


def relocation_chart(chart, location):
    """Keep the natal instant/planet positions; recast only houses and angles."""
    from astral_nexus_mcp.engines.astrology_options import Relocation, AstrologyOptions
    place = Relocation.model_validate(location)
    selected = AstrologyOptions.model_validate(chart.get('calculation_options') or {})
    with LOCK:
        try:
            cusps, angles = swe.houses(chart['julian_day_ut'], place.latitude, place.longitude, selected.house_system.encode())
        except swe.Error as exc:
            raise CalculationError('HOUSE_CALCULATION_FAILED', '此地点无法使用所选宫位制计算迁居盘') from exc
    return {'location': place.model_dump(), 'houses': [{'number':i+1,'longitude':round(cusps[i]%360,6)} for i in range(12)],
            'angles': {'ascendant':round(angles[0]%360,6),'midheaven':round(angles[1]%360,6)},
            'planet_houses': {p['id']:_house(p['longitude'],cusps) for p in chart['planets']}}
