"""Restricted per-relationship review of visible-stem 制 and 化 states."""
from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import DISTANCE_WEIGHT, PILLARS, audit as audit_inputs
from astral_nexus_mcp.engines.bazi_shengke_tongguan_audit import PATHS, audit as audit_tongguan

VERSION = 'bazi-shengke-zhihua-audit-1'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '只核对透干定向关系的第三方制／化状态；合化、优先级和分配未执行。',
            'relationships': [], 'priority_order': None, 'allocations': None,
            'totals_after': None}


def _level(strength):
    return 'full' if strength >= 1.5 else 'partial' if strength >= .3 else 'none'


def _is_middle(actor_index, other_index, target_index):
    return (actor_index, other_index, target_index) in PATHS


def audit(pillars: list[dict], reverse_pass: dict, priority_inputs: dict, tongguan: dict):
    canonical_inputs = audit_inputs(pillars, reverse_pass)
    if (canonical_inputs['status'] != 'inputs_only' or priority_inputs != canonical_inputs):
        return _stop('前序透干关系输入缺失或与逐干余额不一致。')
    canonical_tongguan = audit_tongguan(pillars, reverse_pass, canonical_inputs)
    if (canonical_tongguan['status'] != 'structural_review' or tongguan != canonical_tongguan):
        return _stop('前序通关路径状态缺失或与透干关系不一致。')
    rows = reverse_pass['visible_balances_after']
    visible = {(row['pillar'], row['stem']): row['score'] for row in rows}
    results = []
    for relation in canonical_inputs['relationships']:
        actor_index = PILLARS.index(relation['actor_pillar'])
        target_index = PILLARS.index(relation['target_pillar'])
        actor = pillars[actor_index]
        target = pillars[target_index]
        actor_element = LunarUtil.WU_XING_GAN[actor['stem']]
        target_element = LunarUtil.WU_XING_GAN[target['stem']]
        actor_score = visible[(actor['id'], actor['stem'])]
        direct_control, direct_drain = 0.0, 0.0
        control_sources, drain_sources = [], []
        control_multiplier, drain_multiplier = 1.0, 1.0
        control_multiplier_reason, drain_multiplier_reason = None, None
        # Legacy side-position scan excludes an exact configured middle path.
        for other_index, other in enumerate(pillars):
            if other_index in (actor_index, target_index) or _is_middle(actor_index, other_index, target_index):
                continue
            other_element = LunarUtil.WU_XING_GAN[other['stem']]
            other_score = visible[(other['id'], other['stem'])]
            if CONTROLS[other_element] == actor_element and other_score > actor_score * 1.1:
                control_multiplier = 1.2
                control_multiplier_reason = {'kind': 'side_control', 'pillar': other['id']}
            if GENERATES[actor_element] == other_element:
                drain_multiplier = 1.2
                drain_multiplier_reason = {'kind': 'side_drain', 'pillar': other['id']}
        # Exact configured path takes precedence over the side-position factor.
        for start, middle_index, end in PATHS:
            if (start, end) != (actor_index, target_index):
                continue
            middle = pillars[middle_index]
            middle_element = LunarUtil.WU_XING_GAN[middle['stem']]
            middle_score = visible[(middle['id'], middle['stem'])]
            if CONTROLS[middle_element] == actor_element:
                control_multiplier = 1.3
                control_multiplier_reason = {'kind': 'middle_control', 'pillar': middle['id']}
            if (CONTROLS[actor_element] == target_element and
                    GENERATES[actor_element] == middle_element and
                    GENERATES[middle_element] == target_element and middle_score > 0):
                drain_multiplier = 1.3
                drain_multiplier_reason = {'kind': 'middle_mediation', 'pillar': middle['id']}
            elif GENERATES[actor_element] == middle_element and middle_element != target_element:
                drain_multiplier = 1.2
                drain_multiplier_reason = {'kind': 'middle_drain', 'pillar': middle['id']}
        for other_index, other in enumerate(pillars):
            if other_index in (actor_index, target_index):
                continue
            other_element = LunarUtil.WU_XING_GAN[other['stem']]
            other_score = visible[(other['id'], other['stem'])]
            distance_weight = DISTANCE_WEIGHT[abs(other_index - actor_index)]
            if CONTROLS[other_element] == actor_element:
                strength = other_score / actor_score * distance_weight
                direct_control += strength
                control_sources.append({'pillar': other['id'], 'stem': other['stem'],
                                        'score': round(other_score, 6),
                                        'distance_weight': distance_weight,
                                        'strength': round(strength, 6)})
            if GENERATES[actor_element] == other_element:
                strength = other_score / actor_score * distance_weight
                direct_drain += strength
                drain_sources.append({'pillar': other['id'], 'stem': other['stem'],
                                      'score': round(other_score, 6),
                                      'distance_weight': distance_weight,
                                      'strength': round(strength, 6)})
        control_strength = direct_control * control_multiplier
        drain_strength = direct_drain * drain_multiplier
        results.append({
            'actor_pillar': actor['id'], 'actor_stem': actor['stem'],
            'target_pillar': target['id'], 'target_stem': target['stem'],
            'relation': relation['relation'],
            'control': {'sources': control_sources, 'direct_strength': round(direct_control, 6),
                        'path_multiplier': control_multiplier,
                        'multiplier_reason': control_multiplier_reason,
                        'strength': round(control_strength, 6), 'status': _level(control_strength)},
            'drain': {'sources': drain_sources, 'direct_strength': round(direct_drain, 6),
                      'path_multiplier': drain_multiplier,
                      'multiplier_reason': drain_multiplier_reason,
                      'strength': round(drain_strength, 6), 'status': _level(drain_strength)}})
    return {'version': VERSION, 'status': 'structural_review',
            'reason': '已复算逐关系第三方透干制／化来源、路径系数及旧状态门槛。',
            'scope': '只核对透干定向关系的第三方制／化状态；合化、优先级和分配未执行。',
            'relationships': results, 'priority_order': None, 'allocations': None,
            'totals_after': None}
