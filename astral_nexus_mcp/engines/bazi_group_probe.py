"""Review and replay one isolated 三会/三合 group on initial branch weights."""
import json
from collections import Counter
from math import isfinite
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_branch_replay import MONTH_RATIOS, _strength_status
from astral_nexus_mcp.engines.bazi_interactions import MONTH_STATUS, audit as audit_interactions
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES, calculate_partial

RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_group_v1.json').read_text())
AUDIT_VERSION = 'bazi-group-audit-1'
PROBE_VERSION = 'bazi-group-probe-1'
PILLARS = ('year', 'month', 'day', 'hour')
FIVE = '木火土金水'


def _stop(reason, *, probe=False, candidates=None):
    result = {'version': PROBE_VERSION if probe else AUDIT_VERSION,
              'status': 'not_covered', 'reason': reason,
              'scope': '只核对前序三会／三合；单组探针不是完整地支阶段。',
              'candidates': candidates or [], 'first_group': None,
              'totals_before': None, 'totals_after': None}
    if probe:
        result.update({'converted': [], 'received': [], 'hidden_balances_after': None,
                       'full_branch_totals': None})
    return result


def audit(pillars, partial, interactions):
    try:
        if len(pillars) != 4 or [p['id'] for p in pillars] != list(PILLARS):
            raise ValueError('四柱顺序不完整')
        if partial != calculate_partial(pillars):
            raise ValueError('初始逐干权重与四柱不一致')
        if interactions['branch_events'] != audit_interactions(pillars, partial)['branch_events']:
            raise ValueError('地支候选与四柱不一致')
        candidates = []
        branches = [p['branch'] for p in pillars]
        for kind in ('sanhui', 'sanhe'):
            for group in RULES[kind]['groups']:
                if not all(branch in branches for branch in group):
                    continue
                key = ''.join(group)
                info = RULES[kind]['details'][key]
                positions = [p['id'] for p in pillars if p['branch'] in group]
                candidates.append({'kind': kind, 'rule_key': key,
                                   'target_element': info['合化'],
                                   'positions': positions,
                                   'duplicate_participant': len(positions) != 3})
        if not candidates:
            return {'version': AUDIT_VERSION, 'status': 'no_candidate',
                    'reason': '四支中无完整三会或三合组。',
                    'scope': '只核对前序三会／三合；单组探针不是完整地支阶段。',
                    'candidates': [], 'first_group': None,
                    'totals_before': None, 'totals_after': None}
        if len(candidates) != 1 or candidates[0]['duplicate_participant']:
            return _stop('多组会合或参与支重复，尚未覆盖旧占用与重复支分数归属。',
                         candidates=candidates)
        first = candidates[0]
        target = first['target_element']
        month_status = MONTH_STATUS[pillars[1]['branch']][target]
        raw_month = MONTH_RATIOS[month_status]
        month_coefficient = max(.5, min(1., .5 + (raw_month-.6)*.7/1.2*.7))
        strength = _strength_status(target, partial['totals_before'])
        strength_coefficient = {'强旺': 1., '一般': .8, '偏弱': .7, '衰弱': .6}[strength]
        resonance = RULES[first['kind']]['resonance_factor'] * month_coefficient * strength_coefficient
        first = {**first, 'month_status': month_status,
                 'legacy_group_grade': '完全' if month_status in ('旺', '相') else '部分',
                 'raw_month_ratio': raw_month, 'month_coefficient': month_coefficient,
                 'strength_status': strength, 'strength_coefficient': strength_coefficient,
                 'resonance_coefficient': resonance}
        return {'version': AUDIT_VERSION, 'status': 'single_group_review',
                'reason': '按旧配置顺序识别唯一三会／三合组并核对月令与初始力量因子。',
                'scope': '只核对前序三会／三合；单组探针不是完整地支阶段。',
                'candidates': candidates, 'first_group': first,
                'totals_before': partial['totals_before'], 'totals_after': None}
    except (KeyError, TypeError, ValueError) as exc:
        return _stop(str(exc))


def replay(pillars, partial, interactions, audit_result):
    canonical = audit(pillars, partial, interactions)
    if canonical['status'] != 'single_group_review' or audit_result != canonical:
        return _stop('单组会合审核未完整核对。', probe=True)
    first = canonical['first_group']
    group = RULES[first['kind']]['groups'][next(i for i, group in
             enumerate(RULES[first['kind']]['groups']) if ''.join(group) == first['rule_key'])]
    target = first['target_element']
    by_branch = {p['branch']: p for p in pillars if p['branch'] in group}
    scores = {(row['pillar'], row['stem']): row['base'] for row in partial['components']
              if row['position'] == 'hidden'}
    converted, received = [], []
    converted_total = 0.
    for branch in group:
        pillar = by_branch[branch]
        for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items():
            element = LunarUtil.WU_XING_GAN[stem]
            if element == target or scores[(pillar['id'], stem)] <= 0:
                continue
            before = scores[(pillar['id'], stem)]
            amount = before * RULES['qi_transfer_ratio'][qi]
            scores[(pillar['id'], stem)] = before - amount
            converted_total += amount
            converted.append({'pillar': pillar['id'], 'branch': branch, 'stem': stem,
                              'element': element, 'qi': qi, 'before': round(before, 6),
                              'amount': round(amount, 6), 'after': round(before-amount, 6)})
    receivers = []
    for branch in group:
        pillar = by_branch[branch]
        for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items():
            if LunarUtil.WU_XING_GAN[stem] == target:
                receivers.append((pillar['id'], branch, stem, qi,
                                  RULES['qi_transfer_ratio'][qi]))
    total_weight = sum(row[4] for row in receivers)
    if converted_total and total_weight <= 0:
        return _stop('转出能量无已核对的化神藏干接收项。', probe=True)
    for pillar_id, branch, stem, qi, weight in receivers:
        before = scores[(pillar_id, stem)]
        if before <= 0:
            continue
        resonance_amount = before * (first['resonance_coefficient']-1)
        received_amount = converted_total * weight/total_weight
        after = before + resonance_amount + received_amount
        if not isfinite(after) or after < 0:
            return _stop('化神藏干作用后余额无效。', probe=True)
        scores[(pillar_id, stem)] = after
        received.append({'pillar': pillar_id, 'branch': branch, 'stem': stem,
                         'element': target, 'qi': qi, 'weight': weight,
                         'before': round(before, 6),
                         'resonance_amount': round(resonance_amount, 6),
                         'received_amount': round(received_amount, 6),
                         'after': round(after, 6)})
    totals = Counter()
    for row in partial['components']:
        value = (row['base'] if row['position'] == 'visible' else
                 scores[(row['pillar'], row['stem'])])
        totals[row['element']] += value
    return {'version': PROBE_VERSION, 'status': 'isolated_first_group',
            'reason': '唯一会合组两层公式已局部重放；后续六合、冲刑、空亡等未执行。',
            'scope': '只核对前序三会／三合；单组探针不是完整地支阶段。',
            'candidates': canonical['candidates'], 'first_group': first,
            'converted': converted, 'received': received,
            'hidden_balances_after': [dict(row, score=scores[(row['pillar'], row['stem'])])
                                      for row in partial['components'] if row['position'] == 'hidden'],
            'converted_total': round(converted_total, 6),
            'totals_before': partial['totals_before'],
            'totals_after': {element: round(totals[element], 6) for element in FIVE},
            'full_branch_totals': None}
