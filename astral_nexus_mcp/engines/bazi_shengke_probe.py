"""One auditable first-operation probe; never a complete sheng-ke allocation."""
import json
from collections import Counter
from math import isclose, isfinite
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-shengke-probe-2'
PILLARS = ('year', 'month', 'day', 'hour')
GENERATES = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
CONTROLS = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
YANG = set('甲丙戊庚壬')
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_shengke_first_v1.json').read_text())


def _stop(reason, inputs=None):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅审核旧生克第一段首个日柱本气作用；不输出生克阶段汇总或最终力量。',
            'inputs': inputs, 'first_operation': None, 'totals_after': None}


def _normal_level(relation, global_ratio, current_ratio, actor_has_root):
    """Ordered, main-qi conditions from the legacy config; abnormal grades stop."""
    if relation == '生':
        if not actor_has_root and global_ratio <= 0.3 and current_ratio <= 0.3:
            return None, '可能触发“泄过为克”，异常生克尚未审核。'
        if global_ratio >= 1.5 and current_ratio >= 1.8:
            return '强生', None
        if global_ratio >= 1.2 and current_ratio >= 1.2:
            return '中生', None
        # The main-qi target itself supplies the old "either side has root"
        # condition for normal generation levels.
        if ((global_ratio > 0.3 and current_ratio > 0.3) or
                (global_ratio > 0.1 and current_ratio > 0.1)):
            return '弱生', None
    else:
        if global_ratio <= 0.2 and current_ratio < 0.2:
            return None, '可能触发“反克”，异常生克尚未审核。'
        # The target is positive main qi, so the old "either side has root"
        # condition is true. Retain the ordered strong/medium/weak predicates.
        if (global_ratio >= 1.5 and current_ratio >= 1.0) or (
                global_ratio >= 2 and current_ratio >= 1.5):
            return '强克', None
        if (global_ratio < 2.5 and current_ratio >= 0.5) or (
                global_ratio < 2 and current_ratio >= 0.8):
            return '中克', None
        if (global_ratio < 1.5 and current_ratio >= 0.1) or (
                global_ratio < 1.2 and current_ratio >= 0.2):
            return '弱克', None
    return None, '首个关系未达到已审核的常规生克等级，停止出数。'


def probe(pillars: list[dict], tonggen: dict):
    """Replay one normal same-polarity day-stem to day-main-qi operation."""
    if tonggen.get('status') != 'isolated_tonggen_stage':
        return _stop('前序地支、五合、长生、月令或通根阶段未完整复算。')
    if len(pillars) != 4 or [p.get('id') for p in pillars] != list(PILLARS):
        return _stop('四柱顺序不完整。')
    visible_rows = tonggen.get('visible_balances_after')
    hidden_rows = tonggen.get('hidden_balances_after')
    totals = tonggen.get('totals_after')
    if not isinstance(visible_rows, list) or not isinstance(hidden_rows, list) or not isinstance(totals, dict):
        return _stop('前序逐干余额或汇总缺失。')
    expected_visible = {(p['id'], p['stem']) for p in pillars}
    expected_hidden = {(p['id'], stem) for p in pillars for stem in WEIGHT_RULES['branch_qi_type'][p['branch']]}
    try:
        visible = {(r['pillar'], r['stem']): r for r in visible_rows}
        hidden = {(r['pillar'], r['stem']): r for r in hidden_rows}
        if (len(visible_rows) != 4 or len(hidden_rows) != len(expected_hidden) or
                set(visible) != expected_visible or set(hidden) != expected_hidden or
                set(totals) != set('木火土金水')):
            return _stop('前序逐干项目与四柱不一致。')
        sums = Counter()
        for row in visible_rows + hidden_rows:
            pillar = pillars[PILLARS.index(row['pillar'])]
            stem = row['stem']
            score = row['score']
            if (row['element'] != LunarUtil.WU_XING_GAN[stem] or
                    not isinstance(score, (int, float)) or not isfinite(score) or score < 0 or
                    ('branch' in row and (row['branch'] != pillar['branch'] or
                     row['qi'] != WEIGHT_RULES['branch_qi_type'][pillar['branch']][stem]))):
                return _stop('前序逐干属性或余额无效。')
            sums[row['element']] += score
        if any(not isinstance(totals[e], (int, float)) or not isfinite(totals[e]) or
               not isclose(sums[e], totals[e], abs_tol=0.000002) for e in '木火土金水'):
            return _stop('前序逐干余额与五行汇总不一致。')
    except (KeyError, ValueError, TypeError):
        return _stop('前序逐干项目缺失或无法核对。')

    day = pillars[2]
    main = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][day['branch']].items() if qi == '本气')
    actor, target = day['stem'], main
    actor_element, target_element = LunarUtil.WU_XING_GAN[actor], LunarUtil.WU_XING_GAN[target]
    actor_score = visible[('day', actor)]['score']
    target_score = hidden[('day', target)]['score']
    inputs = {'actor': f'day:{actor}', 'target': f'day:{day["branch"]}:{target}',
              'actor_score': actor_score, 'target_score': target_score,
              'actor_element_total': totals[actor_element], 'target_element_total': totals[target_element]}
    relation = ('生' if GENERATES[actor_element] == target_element else
                '克' if CONTROLS[actor_element] == target_element else None)
    if relation is None:
        return _stop('首个日柱本气无已审核的透干生克关系；其余关系尚未审核。', inputs)
    if min(actor_score, target_score, totals[target_element]) <= 0:
        return _stop('首个关系的分数或分母非正，不能用零值代替。', inputs)
    ratio_global = totals[actor_element] / totals[target_element]
    ratio_current = actor_score / target_score
    inputs.update({'ratio_global': round(ratio_global, 6), 'ratio_current': round(ratio_current, 6)})
    if ((actor in YANG) != (target in YANG) and
            ratio_global > .8 and ratio_current > .8):
        return _stop('异阴阳且两项比值均大于 0.8；旧误传会改变系数。', inputs)
    actor_has_root = any(row['element'] == actor_element and row['score'] > 0 for row in hidden_rows)
    inputs['actor_has_root'] = actor_has_root
    level, stop_reason = _normal_level(relation, ratio_global, ratio_current, actor_has_root)
    if level is None:
        return _stop(stop_reason, inputs)
    config = RULES['normal_levels'][relation][level]
    polarity = RULES['same_yin_yang_generate' if relation == '生' else 'same_yin_yang_control']
    delta = min(actor_score, target_score) * config['coefficient'] * polarity * RULES['common_adjustment']
    actor_change = delta * config['actor_delta_ratio'] * RULES['actor_loss']
    target_change = delta * config['target_delta_ratio']
    return {'version': VERSION, 'status': 'isolated_first_operation',
            'reason': f'仅复算旧流程第一段先处理的日柱本气{level}作用。',
            'scope': '单次局部作用；后续藏干、反向关系与透干优先级分配均未复算。',
            'inputs': inputs,
            'first_operation': {'relation': relation, 'level': level, 'base_delta': round(delta, 6),
                                'actor_before': round(actor_score, 6),
                                'actor_change': round(actor_change, 6),
                                'actor_after': round(actor_score + actor_change, 6),
                                'target_before': round(target_score, 6),
                                'target_change': round(target_change, 6),
                                'target_after': round(target_score + target_change, 6)},
            'totals_after': None}
