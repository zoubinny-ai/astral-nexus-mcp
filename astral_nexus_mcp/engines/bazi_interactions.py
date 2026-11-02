"""Locate branch relations and sheng-ke inputs without applying unreviewed scores."""
from itertools import combinations
import json
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.birth_time import CalculationError

VERSION = 'bazi-interaction-audit-2'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_interactions_v1.json').read_text())
MONTH_STATUS = json.loads((Path(__file__).parent / 'data' / 'bazi_month_status_v1.json').read_text())
PILLAR_IDS = ('year', 'month', 'day', 'hour')
STAGES = (
    (1, 'sanhui', '三会'), (1, 'sanhe', '三合'), (2, 'liuhe', '六合'),
    (3, 'chong', '六冲'), (4, 'sanxing', '三刑'), (5, 'banhe', '半合'),
    (7, 'xing', '相刑'), (8, 'gonghe', '拱合'), (9, 'hai', '相害'), (10, 'po', '相破'),
)
GENERATES = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
CONTROLS = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
PAIR_PRIORITY = ((1, 2), (0, 1), (2, 3), (1, 3), (0, 2), (0, 3))


def _validate_rules():
    if set(RULES) != {name for _, name, _ in STAGES}:
        raise ValueError('Incomplete branch relation catalog')
    branches = set(LunarUtil.ZHI_HIDE_GAN)
    for stage, entries in RULES.items():
        if not isinstance(entries, dict):
            raise ValueError(f'Invalid {stage} catalog')
        for key, info in entries.items():
            if len(key) not in (2, 3) or any(branch not in branches for branch in key):
                raise ValueError(f'Invalid {stage} relation {key}')
            if set(info) != {'type', 'possible_element', 'target_elements', 'target_status'} or not isinstance(info['type'], str):
                raise ValueError(f'Invalid {stage} relation metadata')
    if set(MONTH_STATUS) != branches or any(set(row) != set(GENERATES) for row in MONTH_STATUS.values()):
        raise ValueError('Incomplete month status catalog')


_validate_rules()


def _matching_positions(branches, key):
    """Match distinct pillar positions; duplicate branch characters need distinct pillars."""
    seen = set()
    for positions in combinations(range(4), len(key)):
        if sorted(branches[index] for index in positions) == sorted(key):
            seen.add(positions)
    return sorted(seen)


def _review_conditions(event, pillars, month_branch, prior_full_xing):
    """Review old structural gates, without assuming an event or calculating a delta."""
    kind = event['kind']
    if kind not in ('liuhe', 'banhe', 'chong', 'xing', 'gonghe', 'hai', 'po'):
        return {'coverage': 'not_reviewed'}
    info = RULES[kind][event['rule_key']]
    elements = ([event['possible_element']] if kind in ('liuhe', 'banhe', 'gonghe')
                else info['target_elements'])
    if len(elements) != 1 or elements[0] not in GENERATES:
        return {'coverage': 'needs_strength_target_review'}
    element = elements[0]
    month_status = MONTH_STATUS[month_branch][element]
    month_support = month_status in ('旺', '相')
    exposed = [pillar['id'] for pillar in pillars if pillar['id'] != 'day'
               and LunarUtil.WU_XING_GAN[pillar['stem']] == element]
    positions = {PILLAR_IDS.index(pillar) for pillar in event['pillars']}
    overlaps_prior_xing = [PILLAR_IDS[index] for index in sorted(positions & prior_full_xing)] if kind == 'gonghe' else []
    if kind in ('liuhe', 'banhe'):
        # Tougan and strength select full vs partial only after both structural
        # gates pass. If either fails, the old code sets ratio_factor to zero.
        grade = 'possible_if_reached' if event['adjacent'] and month_support else 'none_if_reached'
        return {'coverage': 'zero_effect_structure_only', 'target_element': element,
                'month_status': month_status, 'month_support': month_support,
                'grade_if_reached': grade, 'numeric_effect': None}
    if kind != 'gonghe':
        if event['adjacent'] and (month_support or info['target_status'] == '减'):
            grade = 'complete_if_reached'
        elif event['adjacent'] or month_support or info['target_status'] == '减':
            grade = 'partial_if_reached'
        else:
            grade = 'none_if_reached'
    elif event['adjacent'] and month_support and exposed:
        grade = 'complete_if_reached'
    elif event['adjacent'] and month_support:
        grade = 'partial_if_reached'
    else:
        grade = 'none_if_reached'
    return {'coverage': 'structural_conditions_only', 'target_element': element,
            'month_status': month_status, 'month_support': month_support,
            'exposed_non_day_stems': exposed, 'grade_if_reached': grade,
            'overlaps_prior_full_xing_positions': overlaps_prior_xing,
            'numeric_effect': None}


def audit(pillars: list[dict], partial: dict):
    """Return candidate event order and available five-element inputs, never an effect."""
    try:
        if len(pillars) != 4 or tuple(p['id'] for p in pillars) != PILLAR_IDS:
            raise ValueError('pillar order')
        branches = [p['branch'] for p in pillars]
        if any(branch not in LunarUtil.ZHI_HIDE_GAN for branch in branches):
            raise ValueError('branch')
        if partial['version'] != 'bazi-strength-partial-1' or partial['month_branch'] != branches[1]:
            raise ValueError('partial source')
        events = []
        for stage_index, stage, label in STAGES:
            for key, info in RULES[stage].items():
                for positions in _matching_positions(branches, key):
                    # The old 三刑 stage only handles full groups; paired 刑 is a later stage.
                    if stage == 'sanxing' and len(key) != 3:
                        continue
                    if stage == 'xing' and len(key) != 2:
                        continue
                    events.append({
                        'stage': stage_index, 'kind': stage, 'label': label,
                        'rule_key': key, 'type': info['type'],
                        'pillars': [PILLAR_IDS[index] for index in positions],
                        'branches': [branches[index] for index in positions],
                        'adjacent': max(positions) - min(positions) == len(positions) - 1,
                        'possible_element': info['possible_element'],
                        'status': 'candidate_only',
                    })
        priority = {tuple(sorted(pair)): index for index, pair in enumerate(PAIR_PRIORITY)}
        events.sort(key=lambda event: (event['stage'],
                                       priority.get(tuple(sorted(PILLAR_IDS.index(p) for p in event['pillars'])), 99),
                                       event['rule_key']))
        prior_full_xing = set()
        for event in events:
            review = _review_conditions(event, pillars, branches[1], prior_full_xing)
            event['condition_review'] = review
            if event['kind'] == 'xing' and review.get('grade_if_reached') == 'complete_if_reached':
                prior_full_xing.update(PILLAR_IDS.index(p) for p in event['pillars'])
        components = partial['components']
        element_inputs = {
            element: {
                'visible': [c['pillar'] + ':' + c['stem'] for c in components
                            if c['element'] == element and c['position'] == 'visible'],
                'hidden': [c['pillar'] + ':' + c['branch'] + ':' + c['stem'] + ':' + c['qi']
                           for c in components if c['element'] == element and c['position'] == 'hidden'],
                'partial_total': partial['totals_after'][element],
            }
            for element in GENERATES
        }
        available = {element for element, sources in element_inputs.items()
                     if sources['visible'] or sources['hidden']}
        relations = [
            {'kind': kind, 'source_element': source, 'target_element': target,
             'source_has_visible': bool(element_inputs[source]['visible']),
             'target_has_visible': bool(element_inputs[target]['visible']),
             'status': 'candidate_only'}
            for kind, mapping in (('generates', GENERATES), ('controls', CONTROLS))
            for source, target in mapping.items() if source in available and target in available
        ]
        return {
            'version': VERSION,
            'branch_events': events,
            'branch_scope': '按旧表顺序发现候选；两支关系与拱合复核月令、相邻、透干及先行相刑重叠。多作用五行的目标需按阶段分数选择；会合、空亡等仍未全量复算。',
            'shengke_inputs': element_inputs,
            'shengke_relations': relations,
            'shengke_scope': '仅列出五行生克方向和可用透藏输入；藏干激活、作用对象、优先级及分配量均待审，不是实际生克事件。',
            'effects_applied': False,
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise CalculationError('INVALID_CHART_REPORT', '地支关系审核输入与基础力量不一致') from exc
