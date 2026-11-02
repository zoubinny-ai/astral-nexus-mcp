"""Audited first possible own-main-qi-to-visible operation, never a full pass."""
import json
from collections import Counter
from math import isclose, isfinite
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES, YANG
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-shengke-reverse-probe-1'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_shengke_reverse_v1.json').read_text())
PILLARS = ('year', 'month', 'day', 'hour')
ORDER = (2, 1, 3, 0)


def _stop(reason, candidate=None, skipped=None):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅审核第一段之后首个本气藏干→本柱透干候选；不输出反向阶段总分。',
            'candidate': candidate, 'skipped': skipped or [], 'operation': None,
            'totals_after': None}


def _normal_level(relation, global_ratio, current_ratio, target_has_root):
    """Legacy reverse table order with a positive main-qi actor."""
    if relation == '生':
        # The actor is positive main qi and rooted, so 泄过为克 cannot match.
        if global_ratio >= 3 and current_ratio >= 3:
            return None, '可能触发“虚不受生”，异常等级尚未审核。'
        if (target_has_root and global_ratio >= 1 and current_ratio >= 1.2) or (
                global_ratio >= 1.5 and current_ratio >= 1.8):
            return '强生', None
        if (target_has_root and global_ratio >= .8 and current_ratio >= .8) or (
                global_ratio >= 1.2 and current_ratio >= 1.2):
            return '中生', None
        if (global_ratio > .3 and current_ratio > .3) or (
                global_ratio > .1 and current_ratio > .1):
            return '弱生', None
    else:
        if global_ratio <= .2 and current_ratio < .2:
            return None, '可能触发“反克”，异常等级尚未审核。'
        if global_ratio >= 2 and current_ratio >= 1.5:
            return '强克', None
        if global_ratio < 2 and current_ratio >= .8:
            return '中克', None
        if global_ratio < 1.2 and current_ratio >= .2:
            return '弱克', None
    return None, '首个反向关系未达到已审核的常规等级。'


def probe(pillars: list[dict], first_pass: dict):
    if first_pass.get('status') != 'isolated_first_pass':
        return _stop('前序生克第一段未完整复算。')
    if len(pillars) != 4 or [p.get('id') for p in pillars] != list(PILLARS):
        return _stop('四柱顺序不完整。')
    visible_rows = first_pass.get('visible_balances_after')
    hidden_rows = first_pass.get('hidden_balances_after')
    source_totals = first_pass.get('totals_after')
    if not isinstance(visible_rows, list) or not isinstance(hidden_rows, list) or not isinstance(source_totals, dict):
        return _stop('前序逐干余额或五行汇总缺失。')
    try:
        expected_visible = {(p['id'], p['stem']) for p in pillars}
        expected_hidden = {(p['id'], stem) for p in pillars for stem in WEIGHT_RULES['branch_qi_type'][p['branch']]}
        visible = {(r['pillar'], r['stem']): r for r in visible_rows}
        hidden = {(r['pillar'], r['stem']): r for r in hidden_rows}
        if (len(visible_rows) != 4 or len(hidden_rows) != len(expected_hidden) or
                set(visible) != expected_visible or set(hidden) != expected_hidden or
                set(source_totals) != set('木火土金水')):
            return _stop('前序逐干项目与四柱不一致。')
        totals = Counter()
        for row, is_hidden in ([(row, False) for row in visible_rows] +
                               [(row, True) for row in hidden_rows]):
            pillar = pillars[PILLARS.index(row['pillar'])]
            score = row['score']
            if (row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                    not isinstance(score, (int, float)) or not isfinite(score) or score < 0 or
                    (is_hidden and (row.get('branch') != pillar['branch'] or
                     row.get('qi') != WEIGHT_RULES['branch_qi_type'][pillar['branch']][row['stem']]))):
                return _stop('前序逐干属性或余额无效。')
            totals[row['element']] += score
        if any(not isinstance(source_totals[e], (int, float)) or not isfinite(source_totals[e]) or
               not isclose(totals[e], source_totals[e], abs_tol=.000002) for e in '木火土金水'):
            return _stop('前序逐干余额与五行汇总不一致。')
    except (KeyError, TypeError, ValueError):
        return _stop('前序逐干项目缺失或无法核对。')
    skipped = []
    for index in ORDER:
        pillar = pillars[index]
        main = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][pillar['branch']].items()
                    if qi == '本气')
        actor_element = LunarUtil.WU_XING_GAN[main]
        target_element = LunarUtil.WU_XING_GAN[pillar['stem']]
        relation = ('生' if GENERATES[actor_element] == target_element else
                    '克' if CONTROLS[actor_element] == target_element else None)
        if relation is None:
            skipped.append({'pillar': pillar['id'], 'hidden_stem': main,
                            'visible_stem': pillar['stem'], 'reason': '本气对透干无生克关系。'})
            continue
        actor_score = hidden[(pillar['id'], main)]['score']
        target_score = visible[(pillar['id'], pillar['stem'])]['score']
        candidate = {'pillar': pillar['id'], 'branch': pillar['branch'], 'hidden_stem': main,
                     'visible_stem': pillar['stem'], 'relation': relation,
                     'hidden_before': round(actor_score, 6), 'visible_before': round(target_score, 6),
                     'hidden_element_total': round(totals[actor_element], 6),
                     'visible_element_total': round(totals[target_element], 6)}
        if min(actor_score, target_score, totals[target_element]) <= 0:
            return _stop('反向关系的来源余额或分母非正，不能用零值补齐。', candidate, skipped)
        global_ratio = totals[actor_element] / totals[target_element]
        current_ratio = actor_score / target_score
        same_polarity = (main in YANG) == (pillar['stem'] in YANG)
        target_has_root = any(r['element'] == target_element and r['score'] > 0 for r in hidden_rows)
        candidate.update({'ratio_global': round(global_ratio, 6),
                          'ratio_current': round(current_ratio, 6),
                          'visible_has_root': target_has_root})
        level, reason = _normal_level(relation, global_ratio, current_ratio, target_has_root)
        if level is None:
            return _stop(reason, candidate, skipped)
        config = RULES['normal_levels'][relation][level]
        polarity = RULES[('different_yin_yang_' if not same_polarity and
                          global_ratio > .8 and current_ratio > .8 else
                          'same_yin_yang_') + ('generate' if relation == '生' else 'control')]
        delta = min(actor_score, target_score) * config['coefficient'] * polarity * RULES['common_adjustment']
        hidden_change = delta * config['hidden_delta_ratio']
        visible_change = delta * config['visible_delta_ratio'] * RULES['visible_loss']
        return {'version': VERSION, 'status': 'isolated_first_reverse_operation',
                'reason': f'仅复算首个可作用的本气藏干→透干{level}。',
                'scope': '单次反向局部作用；后续本气、非本气与透干优先级分配未复算。',
                'candidate': candidate, 'skipped': skipped,
                'operation': {'level': level, 'base_delta': round(delta, 6),
                              'hidden_change': round(hidden_change, 6),
                              'hidden_after': round(actor_score + hidden_change, 6),
                              'visible_change': round(visible_change, 6),
                              'visible_after': round(target_score + visible_change, 6)},
                'totals_after': None}
    return _stop('四柱本气对本柱透干均无生克关系。', skipped=skipped)
