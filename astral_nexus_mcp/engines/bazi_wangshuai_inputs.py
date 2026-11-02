"""Reconcile stage balances and replay the audited legacy strength dimensions."""

from math import isfinite

from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.bazi_strength import RULES

VERSION = 'bazi-wangshuai-inputs-3'
FIVE = '木火土金水'
PRODUCER = {'木': '水', '火': '木', '土': '火', '金': '土', '水': '金'}
POINTS = ((0, 0), (5, 8), (20, 15), (30, 19), (100, 20))
MONTH_POINTS = ((0.7, 0), (0.8, 3), (1.0, 6), (1.3, 9), (1.65, 12))
BALANCE_POINTS = ((0, 0), (5, 0.8), (10, 2.4), (15, 4), (20, 5.2),
                  (25, 6.4), (30, 7.2), (50, 8))
SUPPORT_POINTS = ((0, 0), (10, 5), (20, 10), (40, 15), (60, 18), (100, 20))
CONTROL_POINTS = ((0, 20), (20, 15), (40, 12), (60, 9), (80, 6), (100, 0))
RATIO_POINTS = ((0, 0), (0.5, 1.5), (1, 4), (1.5, 5.5),
                (2, 6.8), (3, 7.6), (5, 8))
CLASSES = {
    '印星': ('正印', '偏印'), '比劫': ('比肩', '劫财'),
    '官杀': ('正官', '七杀'), '食伤': ('食神', '伤官'),
    '财星': ('正财', '偏财'),
}
ROOT_WEIGHTS = {'本气': 1.0, '中气': 0.4, '余气': 0.25}
ROOT_STRENGTH = {'本气': 1.0, '中气': 0.6, '余气': 0.3}


def _score(value, points):
    if value <= points[0][0]:
        return float(points[0][1])
    for (left, low), (right, high) in zip(points, points[1:]):
        if value <= right:
            return low + (value-left) / (right-left) * (high-low)
    return float(points[-1][1])


def _structure(pillars: list[dict]) -> dict:
    """Rebuild old structural counters; no missing category means an invented score."""
    indexed = []
    day_stem = pillars[2]['stem']
    for pillar in pillars:
        branch = pillar['branch']
        expected_god = ('日主' if pillar['id'] == 'day'
                        else LunarUtil.SHI_SHEN[day_stem + pillar['stem']])
        if pillar['stem_ten_god'] != expected_god:
            raise ValueError('透干十神与日主不一致')
        hidden = []
        if {row['stem'] for row in pillar['hidden_stems']} != set(RULES['branch_qi_type'][branch]):
            raise ValueError('藏干与地支规则不一致')
        for row in pillar['hidden_stems']:
            if row['ten_god'] != LunarUtil.SHI_SHEN[day_stem + row['stem']]:
                raise ValueError('藏干十神与日主不一致')
            qi = RULES['branch_qi_type'][branch][row['stem']]
            hidden.append({'stem': row['stem'], 'element': LunarUtil.WU_XING_GAN[row['stem']],
                           'ten_god': row['ten_god'], 'qi': qi})
        indexed.append({'stem': pillar['stem'], 'ten_god': pillar['stem_ten_god'],
                        'hidden': hidden})
    classes = {}
    for category, gods in CLASSES.items():
        visible = sum(row['ten_god'] in gods for row in indexed if row['ten_god'] != '日主')
        roots = [hidden for row in indexed for hidden in row['hidden']
                 if hidden['ten_god'] in gods]
        weight = sum(ROOT_WEIGHTS[item['qi']] for item in roots)
        category_element = next((LunarUtil.WU_XING_GAN[row['stem']]
                                 for row in indexed if row['ten_god'] in gods), None)
        if category_element is None:
            category_element = next((item['element'] for item in roots), None)
        # A category absent from the chart has no same-pillar generating event.
        generated = 0 if category_element is None else sum(
            row['ten_god'] in gods and
            any(item['qi'] == '本气' and item['element'] == PRODUCER[category_element]
                for item in row['hidden']) for row in indexed)
        classes[category] = {'visible': visible, 'root_count': len(roots),
                             'root_weight': round(weight, 6), 'generated': generated}
    day_element = LunarUtil.WU_XING_GAN[pillars[2]['stem']]
    root_qi = [item['qi'] for row in indexed for item in row['hidden']
               if item['element'] == day_element]
    base = sum(ROOT_STRENGTH[qi] for qi in root_qi)
    position_bonus = 0.0
    for index, row in enumerate(indexed):
        count = sum(item['element'] == day_element for item in row['hidden'])
        position_bonus += count * (1.0 if index == 2 else 0.8 if index in (1, 3) else 0.6)
    root_total = base * (1 + position_bonus * 0.1)
    same_pillar_main = next(item for item in indexed[2]['hidden'] if item['qi'] == '本气')
    same_pillar_generated = same_pillar_main['element'] == PRODUCER[day_element]
    return {'classes': classes, 'root_qi': root_qi, 'root_total': root_total,
            'same_pillar_generated': same_pillar_generated,
            'same_pillar_main_stem': same_pillar_main['stem']}


def _root_score(value: float) -> float:
    if value >= 1.5:
        return min(12.0, 6 + (value - 1.5) * 3)
    if value >= 1:
        return min(9.0, 3.6 + (value - 1) * 4.8)
    if value >= 0.5:
        return min(6.0, 1.8 + (value - 0.5) * 3.6)
    if value >= 0.1:
        return min(3.0, value * 18)
    return 0.0


def probe(pillars: list[dict], environment: dict) -> dict:
    def stop(reason):
        return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
                'inputs': None, 'day_strength_component': None,
                'balance_component': None, 'month_component': None,
                'stage_components': None, 'stage_score': None,
                'stage_level': None, 'final_strength': None}

    if environment.get('status') != 'isolated_environment_stage':
        return stop('环境阶段未完整复算，不能提取逐干旺衰输入。')
    try:
        visible = environment['visible_balances_after']
        hidden = environment['hidden_balances_after']
        totals = environment['totals_after']
        if len(visible) != 4 or set(totals) != set(FIVE):
            raise ValueError('透干或五行项目不完整')
        if [row['pillar'] for row in visible] != ['year', 'month', 'day', 'hour']:
            raise ValueError('透干柱序不一致')
        if any(row['stem'] != pillar['stem'] for row, pillar in zip(visible, pillars)):
            raise ValueError('透干与四柱不一致')
        expected_hidden = {(pillar['id'], pillar['branch'], item['stem'])
                           for pillar in pillars for item in pillar['hidden_stems']}
        actual_hidden = [(row['pillar'], row['branch'], row['stem']) for row in hidden]
        if len(actual_hidden) != len(expected_hidden) or set(actual_hidden) != expected_hidden:
            raise ValueError('藏干余额与四柱不一致')
        if any(row['qi'] != RULES['branch_qi_type'][row['branch']][row['stem']]
               for row in hidden):
            raise ValueError('藏干气类与规则不一致')
        for row in visible + hidden:
            if not isfinite(row['score']) or row['score'] < 0 or row['element'] != LunarUtil.WU_XING_GAN[row['stem']]:
                raise ValueError('逐干余额无效')
        for element in FIVE:
            if abs(sum(row['score'] for row in visible + hidden if row['element'] == element)-totals[element]) > 0.00001:
                raise ValueError('逐干余额与五行合计不一致')
        total = sum(totals.values())
        if total <= 0:
            raise ValueError('五行合计不得为零')
        element = LunarUtil.WU_XING_GAN[pillars[2]['stem']]
        day_score = visible[2]['score']
        peer = totals[element] - day_score
        if peer < -0.00001:
            raise ValueError('日干超过所属五行合计')
        producer = PRODUCER[element]
        producer_score = totals[producer]
        other_score = total - totals[element] - producer_score
        balance = day_score + max(0.0, peer) + producer_score - other_score
        percent = (day_score + max(0.0, peer)/2) / total * 100
        month_ratio = RULES['month_stem_ratio'][pillars[1]['branch']][pillars[2]['stem']]
        if not isfinite(month_ratio) or month_ratio <= 0:
            raise ValueError('月令日干比例无效')
        structure = _structure(pillars)
        classes = structure['classes']
        def bonus(category, *, visible_weight, generated_weight):
            row = classes[category]
            amount = (row['visible'] * visible_weight + row['root_weight'] +
                      row['generated'] * generated_weight)
            return amount * (1.5 if row['visible'] > 0 and row['root_weight'] >= 1 else 1)
        support_bonus = bonus('印星', visible_weight=1.5, generated_weight=1.2) + bonus(
            '比劫', visible_weight=1.2, generated_weight=1.0)
        control_penalty = sum(bonus(category, visible_weight=1, generated_weight=1)
                              for category in ('官杀', '食伤', '财星'))
        support = totals[element] + producer_score + support_bonus
        control = other_score + control_penalty
        support_percent = support / total * 100
        control_percent = control / total * 100
        # The old code awards 4 by default at a zero denominator; a missing input is
        # stopped above, while an actual zero force remains a separate audited case.
        ratio = support / control if support > 0 and control > 0 else None
        root_score = _root_score(structure['root_total'])
        components = {
            'day_strength': _score(percent, POINTS),
            'support': _score(support_percent, SUPPORT_POINTS),
            'control': _score(control_percent, CONTROL_POINTS),
            'support_control_ratio': _score(ratio, RATIO_POINTS) if ratio is not None else None,
            'balance': _score(balance, BALANCE_POINTS),
            'root': root_score,
            'month': _score(month_ratio, MONTH_POINTS),
            'same_pillar_generation': 5.0 if structure['same_pillar_generated'] else 0.0,
        }
        # Zero-force ratio is an unreviewed old fallback; do not publish a total.
        full = all(value is not None for value in components.values())
        stage_score = int(sum(components.values())) if full else None
        if stage_score is None:
            level = None
        elif stage_score < 15 and structure['root_total'] < 0.8 and len(structure['root_qi']) < 2:
            level = '极弱'
        elif stage_score < 30:
            level = '衰弱'
        elif stage_score < 60:
            level = '偏弱'
        elif stage_score < 80:
            level = '偏旺'
        elif stage_score >= 90 and control_penalty < 3.8:
            level = '极旺'
        else:
            level = '强旺'
        return {'version': VERSION, 'status': 'calculated_strength' if full else 'not_covered',
                'reason': ('统一前序链环境余额已对账，按旧八维公式和等级边界计算日主旺衰。'
                           if full else '生扶或克泄实为零；旧比值默认分不可核验，旺衰总分停算。'),
                'inputs': {'day_element': element, 'day_stem_score': round(day_score, 6),
                           'peer_except_day': round(max(0.0, peer), 6),
                           'producer_element': producer, 'producer_score': round(producer_score, 6),
                           'remaining_three_elements': round(other_score, 6),
                           'total': round(total, 6), 'day_strength_percent': round(percent, 6),
                           'month_ratio': month_ratio, 'balance': round(balance, 6),
                           'support_bonus': round(support_bonus, 6),
                           'control_penalty': round(control_penalty, 6),
                           'support_percent': round(support_percent, 6),
                           'control_percent': round(control_percent, 6),
                           'support_control_ratio': round(ratio, 6) if ratio is not None else None,
                           'root_total': round(structure['root_total'], 6),
                           'root_count': len(structure['root_qi']),
                           'same_pillar_main_stem': structure['same_pillar_main_stem'],
                           'same_pillar_generated': structure['same_pillar_generated'],
                           'classes': classes},
                'day_strength_component': round(_score(percent, POINTS), 6),
                'balance_component': round(_score(balance, BALANCE_POINTS), 6),
                'month_component': round(_score(month_ratio, MONTH_POINTS), 6),
                'stage_components': {key: round(value, 6) if value is not None else None
                                     for key, value in components.items()},
                'stage_score': stage_score, 'stage_level': level,
                'final_strength': {'score': stage_score, 'level': level,
                                   'components': {key: round(value, 6)
                                                  for key, value in components.items()},
                                   'source': 'environment_replay'} if full else None}
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return stop(str(exc))
