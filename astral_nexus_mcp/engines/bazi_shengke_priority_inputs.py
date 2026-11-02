"""Reviewable visible-stem relationship inputs before legacy priority allocation."""
from collections import Counter
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-shengke-priority-inputs-1'
PILLARS = ('year', 'month', 'day', 'hour')
DISTANCE_WEIGHT = {1: 1.0, 2: 0.6, 3: 0.3}


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅透干关系、距离及作用前比值输入；制化、通关、合化和归一化分配待审。',
            'relationships': [], 'priority_order': None, 'allocations': None,
            'totals_after': None}


def audit(pillars: list[dict], reverse_pass: dict):
    if reverse_pass.get('status') not in ('isolated_reverse_pass', 'isolated_group_reverse_pass'):
        return _stop('前序反向本气段未完整复算。')
    if len(pillars) != 4 or [p.get('id') for p in pillars] != list(PILLARS):
        return _stop('四柱顺序不完整。')
    visible_rows = reverse_pass.get('visible_balances_after')
    hidden_rows = reverse_pass.get('hidden_balances_after')
    totals_after = reverse_pass.get('totals_after')
    if not isinstance(visible_rows, list) or not isinstance(hidden_rows, list) or not isinstance(totals_after, dict):
        return _stop('前序逐干余额或汇总缺失。')
    try:
        visible = {(row['pillar'], row['stem']): row for row in visible_rows}
        hidden = {(row['pillar'], row['stem']): row for row in hidden_rows}
        expected_hidden = {(p['id'], stem) for p in pillars
                           for stem in WEIGHT_RULES['branch_qi_type'][p['branch']]}
        if (len(visible_rows) != 4 or set(visible) != {(p['id'], p['stem']) for p in pillars}
                or len(hidden_rows) != len(expected_hidden) or set(hidden) != expected_hidden
                or set(totals_after) != set('木火土金水')):
            return _stop('前序逐干余额与四柱不一致。')
        totals = Counter()
        for row, is_hidden in ([(row, False) for row in visible_rows] +
                               [(row, True) for row in hidden_rows]):
            score = row['score']
            if (row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                    not isinstance(score, (int, float)) or not isfinite(score) or score < 0):
                return _stop('前序逐干属性或余额无效。')
            if is_hidden:
                pillar = pillars[PILLARS.index(row['pillar'])]
                if (row.get('branch') != pillar['branch'] or
                        row.get('qi') != WEIGHT_RULES['branch_qi_type'][pillar['branch']][row['stem']]):
                    return _stop('前序藏干气类或地支不一致。')
            totals[row['element']] += score
        if any(not isinstance(totals_after[e], (int, float)) or not isfinite(totals_after[e]) or
               not isclose(totals[e], totals_after[e], abs_tol=.000002) for e in '木火土金水'):
            return _stop('前序逐干余额与汇总不一致。')
    except (KeyError, TypeError, ValueError):
        return _stop('前序逐干项目缺失或无法核对。')
    relationships = []
    for actor_index, actor in enumerate(pillars):
        actor_element = LunarUtil.WU_XING_GAN[actor['stem']]
        actor_score = visible[(actor['id'], actor['stem'])]['score']
        if actor_score <= 0:
            return _stop('透干来源余额非正；旧代码会跳过该来源，当前输入审计不覆盖。')
        for target_index, target in enumerate(pillars):
            if actor_index == target_index:
                continue
            target_element = LunarUtil.WU_XING_GAN[target['stem']]
            relation = ('生' if GENERATES[actor_element] == target_element else
                        '克' if CONTROLS[actor_element] == target_element else None)
            if relation is None:
                continue
            target_score = visible[(target['id'], target['stem'])]['score']
            if target_score <= 0 or totals[target_element] <= 0:
                return _stop('透干目标余额或五行分母非正，不能以无穷值代入。')
            distance = abs(actor_index - target_index)
            relationships.append({
                'actor_pillar': actor['id'], 'actor_stem': actor['stem'],
                'target_pillar': target['id'], 'target_stem': target['stem'],
                'relation': relation, 'distance': distance,
                'distance_weight': DISTANCE_WEIGHT[distance],
                'actor_before': round(actor_score, 6), 'target_before': round(target_score, 6),
                'actor_element_total': round(totals[actor_element], 6),
                'target_element_total': round(totals[target_element], 6),
                'ratio_global': round(totals[actor_element] / totals[target_element], 6),
                'ratio_current': round(actor_score / target_score, 6)})
    return {'version': VERSION, 'status': 'inputs_only',
            'reason': '已列出透干定向生克关系及分配前输入；综合优先级与分数作用尚未复算。',
            'scope': '仅透干关系、距离及作用前比值输入；制化、通关、合化和归一化分配待审。',
            'relationships': relationships, 'priority_order': None,
            'allocations': None, 'totals_after': None}
