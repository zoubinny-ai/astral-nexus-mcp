"""Month adjustment after reviewed branch, five-he and life-stage stages."""
from collections import Counter
from math import isclose

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES

VERSION = 'bazi-month-replay-1'
PILLARS = ('year', 'month', 'day', 'hour')


def _unavailable(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅复算已覆盖前序阶段后的月令透干和藏干调整；不代表最终五行力量。',
            'month_branch': None, 'rows': [], 'totals_before': None, 'totals_after': None}


def replay(pillars: list[dict], branch_replay: dict, life_stages: dict):
    """Apply the audited month ratio to every individual current stem balance."""
    if (branch_replay['status'] not in ('isolated_pair_stages', 'isolated_group_branch_stage') or
            life_stages['status'] != 'isolated_life_stages'):
        return _unavailable('前序地支或十二长生阶段未完整复算。')
    balances = branch_replay.get('hidden_balances')
    visible = life_stages.get('rows')
    if balances is None or visible is None or len(visible) != 4:
        return _unavailable('前序逐柱透干或藏干余额缺失。')
    expected = {(p['id'], stem) for p in pillars for stem in LunarUtil.ZHI_HIDE_GAN[p['branch']]}
    actual = [(row['pillar'], row['stem']) for row in balances]
    if len(actual) != len(expected) or set(actual) != expected:
        return _unavailable('前序藏干余额与四柱不一致。')
    if [row['pillar'] for row in visible] != list(PILLARS):
        return _unavailable('前序透干余额柱序不一致。')
    for pillar, row in zip(pillars, visible):
        if row['stem'] != pillar['stem'] or row['branch'] != pillar['branch']:
            return _unavailable('前序透干余额与四柱不一致。')
    if any(row['branch'] != pillars[PILLARS.index(row['pillar'])]['branch'] or
           row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
           row['qi'] != RULES['branch_qi_type'][row['branch']][row['stem']]
           for row in balances):
        return _unavailable('前序藏干属性与四柱不一致。')
    source_totals = life_stages.get('totals_after')
    if source_totals is None:
        return _unavailable('前序五行汇总缺失。')
    expected_totals = Counter()
    for row in visible:
        expected_totals[row['element']] += row['after']
    for row in balances:
        expected_totals[row['element']] += row['score']
    if any(not isclose(expected_totals[element], source_totals[element], abs_tol=0.000002)
           for element in '木火土金水'):
        return _unavailable('前序逐干余额与五行汇总不一致。')
    month_branch = pillars[1]['branch']
    ratios = RULES['month_stem_ratio'][month_branch]
    totals = dict(source_totals)
    rows = []
    for position, sources in (('visible', visible), ('hidden', balances)):
        for source in sources:
            stem = source['stem']
            element = LunarUtil.WU_XING_GAN[stem]
            before = source['after'] if position == 'visible' else source['score']
            raw_ratio = ratios[stem]
            coefficient = max(.5, min(2.5, 1 + (raw_ratio - 1) * .5))
            after = round(before * coefficient, 2)
            delta = after - before
            totals[element] += delta
            rows.append({'pillar': source['pillar'], 'stem': stem,
                         'branch': source['branch'] if position == 'hidden' else None,
                         'position': position, 'qi': source['qi'] if position == 'hidden' else None,
                         'element': element, 'before': before, 'raw_ratio': raw_ratio,
                         'coefficient': coefficient, 'after': after,
                         'delta': round(delta, 6)})
    return {'version': VERSION, 'status': 'isolated_month_stage',
            'reason': '逐干使用前序余额，而非初始权重，复算月令影响。',
            'scope': '仅受限盘的月令阶段快照；通根、生克及最终格局仍未计算。',
            'month_branch': month_branch, 'rows': rows,
            'totals_before': source_totals,
            'totals_after': {element: round(total, 6) for element, total in totals.items()}}
