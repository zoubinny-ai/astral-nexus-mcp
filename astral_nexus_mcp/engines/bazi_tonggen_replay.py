"""Restricted, ordered tonggen replay after the audited month stage."""
import json
from collections import Counter
from math import isclose
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-tonggen-replay-1'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_tonggen_v1.json').read_text())
PILLARS = ('year', 'month', 'day', 'hour')


def _unavailable(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅复算前序已覆盖盘的逐次通根增分；不代表最终五行力量。',
            'events': [], 'visible_balances_after': None, 'hidden_balances_after': None,
            'totals_before': None, 'totals_after': None}


def replay(pillars: list[dict], month_replay: dict):
    """Every visible stem visits all same-element hidden stems in pillar order."""
    if month_replay['status'] != 'isolated_month_stage':
        return _unavailable('前序月令阶段未完整复算。')
    rows = month_replay.get('rows')
    expected_visible = {(p['id'], p['stem']) for p in pillars}
    expected_hidden = {(p['id'], stem) for p in pillars for stem in LunarUtil.ZHI_HIDE_GAN[p['branch']]}
    visible = {(row['pillar'], row['stem']): row['after'] for row in rows if row['position'] == 'visible'}
    hidden = {(row['pillar'], row['stem']): row['after'] for row in rows if row['position'] == 'hidden'}
    if (len(rows) != 4 + len(expected_hidden) or
            len(visible) != 4 or set(visible) != expected_visible or
            len(hidden) != len(expected_hidden) or set(hidden) != expected_hidden):
        return _unavailable('前序逐干余额与四柱不一致。')
    for row in rows:
        pillar = pillars[PILLARS.index(row['pillar'])]
        if (row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                (row['position'] == 'hidden' and
                 (row['branch'] != pillar['branch'] or
                  row['qi'] != WEIGHT_RULES['branch_qi_type'][pillar['branch']][row['stem']]))):
            return _unavailable('前序逐干属性与四柱不一致。')
    source_totals = month_replay.get('totals_after')
    if source_totals is None:
        return _unavailable('前序五行汇总缺失。')
    sums = Counter()
    for row in rows:
        sums[row['element']] += row['after']
    if any(not isclose(sums[element], source_totals[element], abs_tol=0.000002)
           for element in '木火土金水'):
        return _unavailable('前序逐干余额与五行汇总不一致。')
    totals = dict(source_totals)
    events = []
    for i, pillar in enumerate(pillars):
        stem = pillar['stem']
        element = LunarUtil.WU_XING_GAN[stem]
        # The old check_tougan_quantity defaults to excluding the day stem.
        quantity = sum(LunarUtil.WU_XING_GAN[p['stem']] == element
                       for p in pillars if p['id'] != 'day')
        quantity_coeff = RULES['quantity_non_day'].get(str(quantity), RULES['quantity_non_day']['other'])
        for j, branch_pillar in enumerate(pillars):
            branch = branch_pillar['branch']
            for hidden_stem in WEIGHT_RULES['branch_qi_type'][branch]:
                if LunarUtil.WU_XING_GAN[hidden_stem] != element:
                    continue
                position = ('SELF' if i == j else 'NEIGHBOR' if abs(i - j) == 1
                            else 'ADJACENT' if abs(i - j) == 2 else 'REMOTE')
                yin_yang = 'SAME' if (stem in '甲丙戊庚壬') == (hidden_stem in '甲丙戊庚壬') else 'DIFFERENT'
                key = (branch_pillar['id'], hidden_stem)
                hidden_before = hidden[key]
                visible_before = visible[(pillar['id'], stem)]
                gain = (hidden_before * RULES['position'][position] *
                        RULES['yin_yang'][yin_yang] * quantity_coeff)
                enhancement = gain * RULES['hidden_enhancement_ratio']
                visible[(pillar['id'], stem)] += gain
                hidden[key] += enhancement
                totals[element] += gain + enhancement
                events.append({'visible_pillar': pillar['id'], 'visible_stem': stem,
                               'hidden_pillar': branch_pillar['id'], 'branch': branch,
                               'hidden_stem': hidden_stem, 'element': element,
                               'qi': WEIGHT_RULES['branch_qi_type'][branch][hidden_stem],
                               'position': position, 'yin_yang': yin_yang,
                               'non_day_visible_count': quantity,
                               'quantity_coefficient': quantity_coeff,
                               'position_coefficient': RULES['position'][position],
                               'yin_yang_coefficient': RULES['yin_yang'][yin_yang],
                               'visible_before': round(visible_before, 6),
                               'visible_gain': round(gain, 6),
                               'visible_after': round(visible[(pillar['id'], stem)], 6),
                               'hidden_before': round(hidden_before, 6),
                               'hidden_gain': round(enhancement, 6),
                               'hidden_after': round(hidden[key], 6)})
    return {'version': VERSION, 'status': 'isolated_tonggen_stage',
            'reason': '按透干柱序逐次寻找同五行藏干，并将每次藏干增强计入后续匹配。',
            'scope': '仅受限盘的通根阶段快照；生克、环境压制及最终格局仍未计算。',
            'events': events,
            'visible_balances_after': [
                {'pillar': pillar['id'], 'stem': pillar['stem'],
                 'element': LunarUtil.WU_XING_GAN[pillar['stem']],
                 'score': visible[(pillar['id'], pillar['stem'])]}
                for pillar in pillars],
            'hidden_balances_after': [
                {'pillar': pillar['id'], 'branch': pillar['branch'], 'stem': stem,
                 'element': LunarUtil.WU_XING_GAN[stem],
                 'qi': WEIGHT_RULES['branch_qi_type'][pillar['branch']][stem],
                 'score': hidden[(pillar['id'], stem)]}
                for pillar in pillars for stem in WEIGHT_RULES['branch_qi_type'][pillar['branch']]
            ],
            'totals_before': source_totals,
            'totals_after': {element: round(total, 6) for element, total in totals.items()}}
