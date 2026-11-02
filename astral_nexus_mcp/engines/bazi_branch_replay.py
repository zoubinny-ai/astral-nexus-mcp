"""Ordered replay of audited group, pair, punishment and void branch stages."""
import json
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.birth_time import CalculationError
from astral_nexus_mcp.engines.bazi_interactions import GENERATES, CONTROLS, RULES, MONTH_STATUS, audit as audit_interactions
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES, calculate_partial
from astral_nexus_mcp.engines.bazi_kongwang import audit as audit_kongwang

VERSION = 'bazi-branch-replay-8'
PAIR_EFFECTS = json.loads((Path(__file__).parent / 'data' / 'bazi_pair_effects_v1.json').read_text())
SANXING = json.loads((Path(__file__).parent / 'data' / 'bazi_sanxing_v1.json').read_text())
GROUP_RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_group_v1.json').read_text())
MONTH_RATIOS = {'旺': 1.8, '相': 1.5, '休': 1.2, '囚': 0.9, '死': 0.6}
PAIR_KINDS = {'chong': '六冲', 'xing': '相刑', 'hai': '相害', 'po': '相破'}
GONGHE_QI_RATIO = {'本气': .3, '中气': .2, '余气': .1}
HE_QI_RATIO = {'本气': .4, '中气': .25, '余气': .15}
HE_LABELS = {'liuhe': '六合', 'banhe': '半合', 'gonghe': '拱合'}


def _unavailable(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'events': [], 'kongwang_events': [], 'skipped': [], 'hidden_balances': None,
            'totals_before': None, 'totals_after': None}


def _strength_status(element, totals):
    """Reviewed numeric gate from old check_wuxing_strength_status, not day-master strength."""
    seal = next(source for source, target in GENERATES.items() if target == element)
    officer = next(source for source, target in CONTROLS.items() if target == element)
    same = totals[element] + totals[seal]
    total = sum(totals.values())
    if total <= 0:
        return '衰弱'
    other = total - same
    ratio = same / other if other > 0 else float('inf')
    same_share = same / total
    officer_share = totals[officer] / total
    points = (40 if ratio >= 1.2 else 30 if ratio >= .8 else 20 if ratio >= .6 else 10)
    points += (30 if same_share >= .6 else 20 if same_share >= .4 else 15 if same_share >= .3 else 5)
    points += (20 if officer_share <= .2 else 15 if officer_share <= .3 else 10 if officer_share <= .4 else 5)
    points += (10 if same >= 30 else 8 if same >= 20 else 5 if same >= 10 else 2)
    return '强旺' if points >= 80 else '一般' if points >= 60 else '偏弱' if points >= 40 else '衰弱'


def _target_element(event, totals, month_element):
    candidates = RULES[event['kind']][event['rule_key']]['target_elements']
    if not candidates or any(element not in GENERATES for element in candidates):
        return None
    if len(candidates) == 1:
        return candidates[0]
    if month_element in candidates:
        return month_element
    return min(candidates, key=lambda element: totals[element])


def _grade(event, target):
    month_status = MONTH_STATUS[event['month_branch']][target]
    supported = month_status in ('旺', '相')
    decreases = RULES[event['kind']][event['rule_key']]['target_status'] == '减'
    if event['adjacent'] and (supported or decreases):
        return 'complete', month_status
    if event['adjacent'] or supported or decreases:
        return 'partial', month_status
    return 'none', month_status


def _apply_void(pillars, positions, scores, totals, processed_positions):
    changes = []
    for row in positions:
        if not row['is_empty']:
            continue
        if row['pillar'] in processed_positions:
            continue
        for stem in WEIGHT_RULES['branch_qi_type'][row['branch']]:
            element = LunarUtil.WU_XING_GAN[stem]
            old = scores[row['pillar']][element]
            if old <= 0:
                continue
            new = old * .7
            scores[row['pillar']][element] = new
            totals[element] += new - old
            changes.append({'pillar': row['pillar'], 'branch': row['branch'],
                            'stem': stem, 'element': element,
                            'reduction_ratio': .3, 'before': round(old, 6),
                            'after': round(new, 6), 'delta': round(new-old, 6)})
    return changes


def _apply_pair_combination(event, pillars, scores, totals):
    target = event['possible_element']
    if target not in GENERATES:
        return None
    grade = ('complete' if any(
        p['id'] != 'day' and LunarUtil.WU_XING_GAN[p['stem']] == target for p in pillars)
        else 'partial')
    strength = _strength_status(target, totals)
    strength_coeff = {'强旺': 1.0, '一般': .8, '偏弱': .7, '衰弱': .6}[strength]
    factor = (strength_coeff if grade == 'complete' else
              .4 + (strength_coeff - .8) * .5)
    qi_ratios = GONGHE_QI_RATIO if event['kind'] == 'gonghe' else HE_QI_RATIO
    donors = []
    receivers = []
    for pillar_id in event['pillars']:
        branch = next(p['branch'] for p in pillars if p['id'] == pillar_id)
        for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items():
            element = LunarUtil.WU_XING_GAN[stem]
            row = (pillar_id, stem, element, qi_ratios[qi])
            (receivers if element == target else donors).append(row)
    if not receivers:
        return None  # Old fallback credits the total with no hidden-stem recipient.
    changes = []
    converted = 0.0
    for pillar_id, stem, element, qi_ratio in donors:
        old = scores[pillar_id][element]
        amount = old * qi_ratio * factor
        after = old - amount
        scores[pillar_id][element] = after
        totals[element] -= amount
        converted += amount
        changes.append({'pillar': pillar_id, 'stem': stem, 'element': element,
                        'before': round(old, 6), 'after': round(after, 6),
                        'delta': round(-amount, 6)})
    total_weight = sum(row[3] for row in receivers)
    for pillar_id, stem, element, qi_ratio in receivers:
        old = scores[pillar_id][element]
        amount = converted * qi_ratio / total_weight
        after = old + amount
        scores[pillar_id][element] = after
        totals[element] += amount
        changes.append({'pillar': pillar_id, 'stem': stem, 'element': element,
                        'before': round(old, 6), 'after': round(after, 6),
                        'delta': round(amount, 6)})
    label = HE_LABELS[event['kind']]
    return {'kind': event['kind'], 'label': label, 'rule_key': event['rule_key'],
            'pillars': event['pillars'],
            'grade': ('完全' if grade == 'complete' else '部分') + label,
            'target_element': target, 'target_strength_gate': strength,
            'factor': round(factor, 6), 'changes': changes}


def _apply_group(event, pillars, scores, totals):
    """Legacy two-layer group transfer over every matching pillar position."""
    kind, key = event['kind'], event['rule_key']
    target = GROUP_RULES[kind]['details'][key]['合化']
    positions = [p for p in pillars if p['branch'] in key]
    status = MONTH_STATUS[pillars[1]['branch']][target]
    raw_month = MONTH_RATIOS[status]
    month_coeff = max(.5, min(1., .5 + (raw_month-.6)*.7/1.2*.7))
    strength = _strength_status(target, totals)
    strength_coeff = {'强旺': 1., '一般': .8, '偏弱': .7, '衰弱': .6}[strength]
    resonance = GROUP_RULES[kind]['resonance_factor'] * month_coeff * strength_coeff
    changes, converted, receivers = [], 0., []
    for pillar in positions:
        pid, branch = pillar['id'], pillar['branch']
        for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items():
            element = LunarUtil.WU_XING_GAN[stem]
            if element == target:
                receivers.append((pid, stem, qi, GROUP_RULES['qi_transfer_ratio'][qi]))
                continue
            old = scores[pid][element]
            amount = old * GROUP_RULES['qi_transfer_ratio'][qi]
            scores[pid][element] -= amount
            totals[element] -= amount
            converted += amount
            changes.append({'pillar': pid, 'stem': stem, 'element': element,
                            'before': round(old, 6), 'after': round(old-amount, 6),
                            'delta': round(-amount, 6)})
    weight = sum(row[3] for row in receivers)
    if converted and weight <= 0:
        return None
    for pid, stem, qi, ratio in receivers:
        old = scores[pid][target]
        amount = old * (resonance-1) + (converted * ratio / weight if weight else 0)
        after = old + amount
        if after < 0:
            return None
        scores[pid][target] = after
        totals[target] += amount
        changes.append({'pillar': pid, 'stem': stem, 'element': target,
                        'before': round(old, 6), 'after': round(after, 6),
                        'delta': round(amount, 6)})
    label = '三会' if kind == 'sanhui' else '三合'
    return {'kind': kind, 'label': label, 'rule_key': key,
            'pillars': [p['id'] for p in positions],
            'grade': ('完全' if status in ('旺', '相') else '部分') + label,
            'target_element': target, 'target_strength_gate': strength,
            'factor': round(resonance, 6), 'changes': changes}


def _apply_sanxing(event, pillars, scores, totals):
    key = event['rule_key']
    config = SANXING[key]
    positions = [p for p in pillars if p['branch'] in key]
    month_element = _main_element(pillars[1]['branch'])
    targets = config['五行']
    target = (month_element if month_element in targets else
              min(targets, key=lambda element: totals[element]))
    month_status = MONTH_STATUS[pillars[1]['branch']][target]
    strength = _strength_status(target, totals)
    raw_month = MONTH_RATIOS[month_status]
    month_coeff = max(.5, min(1., .5 + (raw_month-.6)*.7/1.2*.7))
    strength_coeff = {'强旺': 1., '一般': .8, '偏弱': .7, '衰弱': .6}[strength]
    factor = month_coeff * strength_coeff if config['状态'] == '加' else 1.
    grade = '完全相刑' if month_status in ('旺', '相') or config['状态'] == '减' else '部分相刑'
    # The legacy table has no partial adjustments for 丑未戌. Its partial
    # event is still recorded, with no numeric transfer.
    effects = config.get(grade, {})
    changes = []
    for pillar in positions:
        pid, branch = pillar['id'], pillar['branch']
        for stem, adjustment in effects.get(branch, {}).items():
            element = LunarUtil.WU_XING_GAN[stem]
            old = scores[pid][element]
            after = old * (1 + adjustment * factor)
            scores[pid][element] = after
            totals[element] += after-old
            changes.append({'pillar': pid, 'stem': stem, 'element': element,
                            'before': round(old, 6), 'after': round(after, 6),
                            'delta': round(after-old, 6)})
    return {'kind': 'sanxing', 'label': '三刑', 'rule_key': key,
            'pillars': [p['id'] for p in positions], 'grade': grade,
            'target_element': target, 'target_strength_gate': strength,
            'factor': round(factor, 6), 'changes': changes}


def _main_element(branch):
    stem = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items()
                if qi == '本气')
    return LunarUtil.WU_XING_GAN[stem]


def replay(pillars: list[dict], partial: dict, interaction_audit: dict):
    """Replay reviewed pairwise stages when group gates are known absent."""
    try:
        if partial != calculate_partial(pillars):
            return _unavailable('初始权重与四柱不一致。')
        if interaction_audit != audit_interactions(pillars, partial):
            return _unavailable('地支关系输入与四柱不一致。')
    except (CalculationError, KeyError, TypeError, ValueError):
        return _unavailable('地支阶段输入缺失或无效。')
    events = interaction_audit['branch_events']
    if any(event['kind'] not in (*PAIR_KINDS, 'gonghe', 'liuhe', 'banhe',
                                 'sanhui', 'sanhe', 'sanxing')
           for event in events):
        return _unavailable('存在尚未重写的会合关系，不能跳过前序作用。')
    kongwang = audit_kongwang(pillars, interaction_audit)
    if kongwang['status'] != 'audited':
        return _unavailable('日柱旬空无法核对：' + kongwang['reason'])
    scores = {pillar['id']: {element: 0.0 for element in GENERATES} for pillar in pillars}
    visible = {element: 0.0 for element in GENERATES}
    for component in partial['components']:
        if component['position'] == 'visible':
            visible[component['element']] += component['base']
        else:
            scores[component['pillar']][component['element']] += component['base']
    totals = {element: visible[element] + sum(row[element] for row in scores.values())
              for element in GENERATES}
    before = {element: round(total, 6) for element, total in totals.items()}
    trace = []
    kongwang_events = []
    skipped = []
    processed_positions = set()
    group_keys = set()
    used_group_branches = set()
    sanxing_applied = False
    month_branch = pillars[1]['branch']
    main_stem = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][month_branch].items() if qi == '本气')
    month_element = LunarUtil.WU_XING_GAN[main_stem]
    void_applied = False
    for event in events:
        if event['stage'] > 5 and not void_applied:
            changes = _apply_void(pillars, kongwang['positions'], scores, totals,
                                  {pillars[index]['id'] for index in processed_positions})
            if changes is None:
                return _unavailable('六冲后重复旬空地支的占用归属不明。')
            kongwang_events.extend(changes)
            void_applied = True
        positions = {('year', 'month', 'day', 'hour').index(pillar) for pillar in event['pillars']}
        if event['kind'] in ('sanhui', 'sanhe'):
            key = event['kind'], event['rule_key']
            if key in group_keys:
                continue
            group_keys.add(key)
            if used_group_branches.intersection(event['rule_key']):
                skipped.append({'kind': event['kind'], 'rule_key': event['rule_key'],
                                'pillars': event['pillars'], 'reason': '先行三会／三合占用参与支'})
                continue
            applied = _apply_group(event, pillars, scores, totals)
            if applied is None:
                return _unavailable('三会／三合转出能量没有可核对的化神藏干接收项。')
            trace.append(applied)
            used_group_branches.update(event['rule_key'])
            if applied['grade'].startswith('完全'):
                processed_positions.update(('year', 'month', 'day', 'hour').index(pid)
                                           for pid in applied['pillars'])
            continue
        if event['kind'] == 'sanxing':
            if sanxing_applied:
                continue
            applied = _apply_sanxing(event, pillars, scores, totals)
            if applied is None:
                return _unavailable('三刑配置缺少对应级别的逐干作用。')
            trace.append(applied)
            sanxing_applied = True
            processed_positions.update(('year', 'month', 'day', 'hour').index(pid)
                                       for pid in applied['pillars'])
            continue
        if event['kind'] == 'xing' and sanxing_applied:
            skipped.append({'kind': 'xing', 'rule_key': event['rule_key'],
                            'pillars': event['pillars'], 'reason': '先行三刑已按旧顺序处理'})
            continue
        if event['kind'] in HE_LABELS:
            if positions & processed_positions or event['condition_review'].get('grade_if_reached') == 'none_if_reached':
                skipped.append({'kind': event['kind'], 'rule_key': event['rule_key'],
                                'pillars': event['pillars'],
                                'reason': '先行完全关系占位' if positions & processed_positions else '不满足会合结构条件'})
                continue
            applied = _apply_pair_combination(event, pillars, scores, totals)
            if applied is None:
                return _unavailable('会合转出能量没有可核对的化神藏干接收项。')
            trace.append(applied)
            if applied['grade'].startswith('完全'):
                processed_positions.update(positions)
            continue
        kind = event['kind']
        if kind in ('hai', 'po') and positions & processed_positions:
            skipped.append({'kind': kind, 'rule_key': event['rule_key'], 'pillars': event['pillars'],
                            'reason': '先行完全关系占位'})
            continue
        target = _target_element(event, totals, month_element)
        if target is None:
            return _unavailable('两支作用目标五行未能确定。')
        grade, month_status = _grade({**event, 'month_branch': month_branch}, target)
        if grade == 'none':
            skipped.append({'kind': kind, 'rule_key': event['rule_key'], 'pillars': event['pillars'],
                            'reason': '不满足作用结构条件'})
            continue
        grade_name = ('完全' if grade == 'complete' else '部分') + PAIR_KINDS[kind]
        effects = PAIR_EFFECTS[kind][event['rule_key']].get(grade_name)
        if not effects:
            return _unavailable('两支作用配置缺少对应级别的作用表。')
        if month_status not in MONTH_RATIOS:
            return _unavailable('月令状态未覆盖。')
        distance = abs(('year', 'month', 'day', 'hour').index(event['pillars'][0]) -
                       ('year', 'month', 'day', 'hour').index(event['pillars'][1]))
        neighbor = {1: 1.0, 2: 0.7, 3: 0.4}[distance]
        status = _strength_status(target, totals)
        strength = {'强旺': 1.0, '一般': .8, '偏弱': .7, '衰弱': .6}[status]
        raw_month = MONTH_RATIOS[month_status]
        month_coeff = max(.5, min(1.0, .5 + (raw_month - .6) * .7 / 1.2 * .7))
        factor = (neighbor if RULES[kind][event['rule_key']]['target_status'] == '减'
                  else month_coeff * strength * neighbor)
        changes = []
        for branch, adjustments in effects.items():
            index = event['branches'].index(branch)
            pillar_id = event['pillars'][index]
            for stem, adjustment in adjustments.items():
                element = LunarUtil.WU_XING_GAN[stem]
                old = scores[pillar_id][element]
                new = old * (1 + adjustment * factor)
                scores[pillar_id][element] = new
                totals[element] += new - old
                changes.append({'pillar': pillar_id, 'stem': stem, 'element': element,
                                'before': round(old, 6), 'after': round(new, 6),
                                'delta': round(new - old, 6)})
        if grade == 'complete':
            processed_positions.update(positions)
        trace.append({'kind': kind, 'label': PAIR_KINDS[kind],
                      'rule_key': event['rule_key'], 'pillars': event['pillars'],
                      'grade': grade_name, 'target_element': target,
                      'target_strength_gate': status, 'factor': round(factor, 6),
                      'changes': changes})
    if not void_applied:
        changes = _apply_void(pillars, kongwang['positions'], scores, totals,
                              {pillars[index]['id'] for index in processed_positions})
        if changes is None:
            return _unavailable('六冲后重复旬空地支的占用归属不明。')
        kongwang_events.extend(changes)
    return {'version': VERSION, 'status': 'isolated_pair_stages',
            'scope': '按旧阶段顺序复算已审地支关系与逐柱藏干；旬空在半合后按占用衰减，未执行后续五合与生克。',
            'events': trace, 'kongwang_events': kongwang_events, 'skipped': skipped,
            'hidden_balances': [
                {'pillar': pillar['id'], 'branch': pillar['branch'], 'stem': stem,
                 'element': LunarUtil.WU_XING_GAN[stem],
                 'qi': WEIGHT_RULES['branch_qi_type'][pillar['branch']][stem],
                 'score': scores[pillar['id']][LunarUtil.WU_XING_GAN[stem]]}
                for pillar in pillars for stem in LunarUtil.ZHI_HIDE_GAN[pillar['branch']]
            ],
            'totals_before': before,
            'totals_after': {element: round(total, 6) for element, total in totals.items()}}
