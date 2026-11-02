"""Restricted legacy stem-status merge and active priority-factor review.

This is a diagnostic ledger, not an allocation or final strength calculation.
"""
from astral_nexus_mcp.engines.bazi_shengke_hehua_event_audit import audit as audit_events
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS

VERSION = 'bazi-shengke-priority-review-1'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅逐干状态合并与主动关系的两套优先级因子；不排序或分配。',
            'stem_statuses': [], 'active_factors': [], 'priority_order': None,
            'allocations': None, 'totals_after': None}


def _strength(row):
    ratio = row['actor_before'] / row['target_before']
    if row['relation'] == '生':
        base = (2.0 if ratio <= .5 else 1.8 if ratio <= .7 else
                1.5 if ratio <= .8 else 1.2 if ratio <= 1 else
                1.0 if ratio <= 1.2 else .8 if ratio <= 1.5 else .5)
    else:
        base = (2.0 if ratio >= 2 else 1.8 if ratio >= 1.5 else
                1.5 if ratio >= 1.2 else 1.2 if ratio >= 1 else
                1.0 if ratio >= .8 else .8 if ratio >= .6 else .5)
    adjustment = min(row['actor_element_total'] / row['target_element_total'], ratio)
    factor = 1.2 if adjustment >= 1.5 else 1.0 if adjustment >= 1 else .8 if adjustment >= .8 else .5
    return max(.1, min(2.0, base * factor))


def audit(pillars, branch_replay, five_he, reverse_pass, inputs, tongguan, zhihua, events):
    canonical = audit_events(pillars, branch_replay, five_he, reverse_pass,
                             inputs, tongguan, zhihua)
    if canonical['status'] != 'event_link_review' or events != canonical:
        return _stop('前序关系、通关、制化或五合事件证据未完整核对。')
    relations = inputs['relationships']
    paired = list(zip(relations, tongguan['paths'], zhihua['relationships'], events['relationships']))
    if any(len(part) != len(relations) for part in (
            tongguan['paths'], zhihua['relationships'], events['relationships'])):
        return _stop('逐关系状态数量不一致。')
    statuses = []
    for pillar in PILLARS:
        own = [item for item in paired if item[0]['actor_pillar'] == pillar]
        control = [item[2]['control'] for item in own]
        drain = [item[2]['drain'] for item in own]
        first_event = own[0][3]['event_link'] if own else None
        last_path = own[-1][1]['path'] if own else None
        statuses.append({
            'pillar': pillar, 'active_targets': [item[0]['target_pillar'] for item in own],
            'control_full': any(s['status'] == 'full' for s in control),
            'control_partial': any(s['status'] == 'partial' for s in control),
            'control_last_nonzero': next(({'target_pillar': item[0]['target_pillar'],
                'strength': item[2]['control']['strength'], 'sources': item[2]['control']['sources']}
                for item in reversed(own) if item[2]['control']['strength'] > 0), None),
            'drain_full': any(s['status'] == 'full' for s in drain),
            'drain_partial': any(s['status'] == 'partial' for s in drain),
            'drain_last_nonzero': next(({'target_pillar': item[0]['target_pillar'],
                'strength': item[2]['drain']['strength'], 'sources': item[2]['drain']['sources']}
                for item in reversed(own) if item[2]['drain']['strength'] > 0), None),
            'hehua_first_relation_link': first_event,
            'tongguan_last_relation_path': last_path,
            'tongguan_overwritten': bool(own and last_path is None and
                                        any(item[1]['path'] for item in own[:-1])),
        })
    by_pillar = {row['pillar']: row for row in statuses}
    factors = []
    for relation, path_row, zh_row, event_row in paired:
        stem = by_pillar[relation['actor_pillar']]
        strength = _strength(relation)
        base = 1.0 if relation['relation'] == '生' else .8
        zhi_initial = .1 if zh_row['control']['status'] == 'full' else .8 if zh_row['control']['status'] == 'partial' else 1.0
        hua_initial = .2 if zh_row['drain']['status'] == 'full' else .8 if zh_row['drain']['status'] == 'partial' else 1.0
        # The legacy path object lacks distance_to_A/B. Its default 0/0 selects 1.5.
        tong_initial = 1.5 if path_row['path'] else 1.0
        event = event_row['event_link']
        he_initial = (.8 if event['actor_is_higher'] else .1) if event else 1.0
        initial = base * relation['distance_weight'] * strength * zhi_initial * hua_initial * tong_initial * he_initial
        combined = (.1 if stem['control_full'] else 1.0) * (.1 if stem['drain_full'] else 1.0)
        if stem['control_partial'] and stem['drain_partial']:
            combined *= .6
        elif stem['control_partial'] or stem['drain_partial']:
            combined *= .8
        first = stem['hehua_first_relation_link']
        he_combined = (.8 if first['actor_is_higher'] else .1) if first else 1.0
        last = stem['tongguan_last_relation_path']
        tong_combined = (1.1 if last['status'] == 'partial' else 1.2) if last else 1.0
        comprehensive = base * relation['distance_weight'] * strength * combined * he_combined * tong_combined
        factors.append({'actor_pillar': relation['actor_pillar'],
                        'target_pillar': relation['target_pillar'], 'relation': relation['relation'],
                        'base': base, 'distance': relation['distance_weight'],
                        'strength': round(strength, 6),
                        'initial_multipliers': {'control': zhi_initial, 'drain': hua_initial,
                                                'tongguan': tong_initial, 'hehua': he_initial},
                        'initial_final_priority': round(initial, 9),
                        'merged_multipliers': {'zhihua': round(combined, 6),
                                               'tongguan': tong_combined, 'hehua': he_combined},
                        'comprehensive_priority': round(comprehensive, 9)})
    return {'version': VERSION, 'status': 'active_factor_review',
            'reason': '逐干状态沿用旧合并顺序；仅列主动关系的初始与综合优先级因子。旧排序使用初始 final_priority，且被动关系列表尚未覆盖。',
            'scope': '仅逐干状态合并与主动关系的两套优先级因子；不排序或分配。',
            'stem_statuses': statuses, 'active_factors': factors,
            'priority_order': None, 'allocations': None, 'totals_after': None}
