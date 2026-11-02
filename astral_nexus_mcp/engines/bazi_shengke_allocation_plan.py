"""Review the legacy relationship order and ratio plan without changing scores."""
from math import isclose

from astral_nexus_mcp.engines.bazi_shengke_priority_review import audit as audit_priority
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS

VERSION = 'bazi-shengke-allocation-plan-2'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '完整主动／被动记录的旧排序与受限比例计划；不执行分数分配。',
            'relationship_order': [], 'ratio_plan': [], 'priority_order': None,
            'allocations': None, 'totals_after': None}


def _passive_strength(row, relation):
    ratio = row['actor_before'] / row['target_before']
    if relation == '被生':
        base = (2.0 if ratio >= 2 else 1.5 if ratio >= 1.5 else
                1.2 if ratio >= 1.2 else 1.0 if ratio >= 1 else
                .8 if ratio >= .8 else .6 if ratio >= .6 else
                .4 if ratio >= .4 else .1)
    else:
        base = (2.0 if ratio <= .5 else 1.8 if ratio <= .7 else
                1.5 if ratio <= .8 else 1.2 if ratio <= 1 else
                1.0 if ratio <= 1.2 else .8 if ratio <= 1.5 else .5)
    adjustment = min(row['actor_element_total'] / row['target_element_total'], ratio)
    factor = 1.2 if adjustment >= 1.5 else 1.0 if adjustment >= 1 else .8 if adjustment >= .8 else .5
    return max(.1, min(2.0, base * factor))


def _initial_multiplier(status):
    return .1 if status == 'full' else .8 if status == 'partial' else 1.0


def _source_multiplier(status, kind, target):
    full, partial = status[f'{kind}_full'], status[f'{kind}_partial']
    if not full and not partial:
        return 1.0
    latest = status[f'{kind}_last_nonzero']
    if latest is None:
        return 1.0
    sources = [source for source in latest['sources'] if source['pillar'] != target]
    if not sources:
        return 1.0
    if full and len(sources) == len(latest['sources']):
        return 0.0
    actor_score = status['score_before']
    return max(0.0, 1.0 - sum(source['score'] / actor_score * source['distance_weight']
                              for source in sources))


def _active_ratio(row, status, target):
    base_ratio = min(max(row['comprehensive_priority'], .8), 1.0)
    control = _source_multiplier(status, 'control', target)
    drain = _source_multiplier(status, 'drain', target)
    last_path = status['tongguan_last_relation_path']
    if last_path and status['active_targets'][-1] != target:
        # The legacy source strength is 1.3: interpolation at 1.3 gives 1.425.
        tongguan = 1.425
    else:
        tongguan = 1.0
    first = status['hehua_first_relation_link']
    if not first:
        hehua = 1.0
    elif not first['actor_is_higher']:
        hehua = 0.0
    elif first['partner_pillar'] != target:
        hehua = 1.0
    else:
        actor_score, target_score = status['score_before'], row['other_before']
        hehua = 1.3 - actor_score / (actor_score + target_score)
    relation_base = 1.0 if row['relation'] == '生' else .9
    raw = base_ratio * relation_base * row['distance'] * row['strength'] * control * drain * tongguan * hehua
    return min(max(raw, 0.0), 1.0), {
        'base_ratio': round(base_ratio, 9), 'relation': relation_base,
        'control': round(control, 9), 'drain': round(drain, 9),
        'tongguan': round(tongguan, 9), 'hehua': round(hehua, 9)}


def _normalize(rows):
    """Mirror the old per-owner positive-ratio normalization; inputs stay immutable."""
    totals = {pillar: sum(row['raw_ratio'] for row in rows
                          if row['owner_pillar'] == pillar and row['raw_ratio'] > 0)
              for pillar in PILLARS}
    normalized = [{**row, 'normalization_factor': round(1 / totals[row['owner_pillar']], 9)
                   if totals[row['owner_pillar']] > 1 else 1.0,
                   'normalized_ratio': round(row['raw_ratio'] / totals[row['owner_pillar']], 9)
                   if totals[row['owner_pillar']] > 1 else row['raw_ratio']}
                  for row in rows]
    for owner in PILLARS:
        if totals[owner] <= 1:
            continue
        indexes = [index for index, row in enumerate(normalized)
                   if row['owner_pillar'] == owner and row['raw_ratio'] > 0]
        if indexes:
            last = indexes[-1]
            residual = round(1 - sum(normalized[index]['normalized_ratio']
                                     for index in indexes[:-1]), 9)
            normalized[last]['normalized_ratio'] = residual
    return normalized


def audit(pillars, branch_replay, five_he, reverse_pass, inputs, tongguan,
          zhihua, events, priority):
    canonical = audit_priority(pillars, branch_replay, five_he, reverse_pass,
                               inputs, tongguan, zhihua, events)
    if canonical['status'] != 'active_factor_review' or priority != canonical:
        return _stop('逐干状态或主动优先级因子未完整核对。')
    pairs = {(row['actor_pillar'], row['target_pillar']): (row, path, zh, event)
             for row, path, zh, event in zip(inputs['relationships'], tongguan['paths'],
                                             zhihua['relationships'], events['relationships'])}
    active = {(row['actor_pillar'], row['target_pillar']): row
              for row in priority['active_factors']}
    if len(pairs) != len(inputs['relationships']) or len(active) != len(pairs):
        return _stop('定向关系无法逐一对应。')
    # Legacy's indirect five-he branch rebinds a local stem used in display
    # labels. Numeric relationship direction, element and allocation remain
    # keyed by the original pillar; those audited values continue below.
    statuses = {row['pillar']: {**row, 'score_before': next(
        visible['score'] for visible in reverse_pass['visible_balances_after']
        if visible['pillar'] == row['pillar'])} for row in priority['stem_statuses']}
    collection = []
    for owner in PILLARS:
        for target in PILLARS:
            if (owner, target) not in pairs:
                continue
            source, path, zh, event = pairs[owner, target]
            factor = active[owner, target]
            collection.append({'owner_pillar': owner, 'other_pillar': target,
                               'direction': 'active', 'relation': source['relation'],
                               'distance': source['distance_weight'],
                               'strength': factor['strength'],
                               'other_before': source['target_before'],
                               'initial_final_priority': factor['initial_final_priority'],
                               'comprehensive_priority': factor['comprehensive_priority']})
        for source_owner in PILLARS:
            if (source_owner, owner) not in pairs:
                continue
            source, path, zh, event = pairs[source_owner, owner]
            relation = '被生' if source['relation'] == '生' else '被克'
            strength = _passive_strength(source, relation)
            base = .9 if relation == '被生' else .6
            event_pair = next((pair for pair in events.get('event_pairs', [])
                               if {owner, source_owner} == set(pair['pillars'])), None)
            hehua = (.8 if owner == event_pair['higher_pillar'] else .1) if (
                event_pair and {owner, source_owner} == set(event_pair['pillars'])) else 1.0
            initial = (base * source['distance_weight'] * strength *
                       _initial_multiplier(zh['control']['status']) *
                       (.2 if zh['drain']['status'] == 'full' else
                        .8 if zh['drain']['status'] == 'partial' else 1.0) *
                       (1.5 if path['path'] else 1.0) * hehua)
            source_status = statuses[source_owner]
            zhi_hua = (.1 if source_status['control_full'] or source_status['control_partial'] else 1.0)
            zhi_hua *= (.3 if source_status['drain_full'] or source_status['drain_partial'] else 1.0)
            owner_status = statuses[owner]
            first = owner_status['hehua_first_relation_link']
            merged_hehua = (.8 if first['actor_is_higher'] else .1) if first else 1.0
            last = owner_status['tongguan_last_relation_path']
            merged_tongguan = (1.1 if last['status'] == 'partial' else 1.2) if last else 1.0
            comprehensive = base * source['distance_weight'] * strength * zhi_hua * merged_hehua * merged_tongguan
            collection.append({'owner_pillar': owner, 'other_pillar': source_owner,
                               'direction': 'passive', 'relation': relation,
                               'distance': source['distance_weight'], 'strength': round(strength, 6),
                               'other_before': source['actor_before'],
                               'initial_final_priority': round(initial, 9),
                               'comprehensive_priority': round(comprehensive, 9)})
    sorted_rows = sorted(collection, key=lambda row: row['initial_final_priority'], reverse=True)
    if any(isclose(left['initial_final_priority'], right['initial_final_priority'], abs_tol=1e-9)
           and left['initial_final_priority'] != right['initial_final_priority']
           for left, right in zip(sorted_rows, sorted_rows[1:])):
        return _stop('初始优先级过近，当前精度不足以可靠复现排序。')
    plans = []
    for rank, row in enumerate(sorted_rows, 1):
        owner = row['owner_pillar']
        if row['direction'] == 'active':
            ratio, multipliers = _active_ratio(row, statuses[owner], row['other_pillar'])
        else:
            ratio, multipliers = 0.0, None  # Legacy 被生／被克 base multiplier is zero.
        plans.append({'rank': rank, 'owner_pillar': owner,
                      'other_pillar': row['other_pillar'], 'relation': row['relation'],
                      'direction': row['direction'], 'raw_ratio': round(ratio, 9),
                      'ratio_multipliers': multipliers})
    normalized = _normalize(plans)
    return {'version': VERSION, 'status': 'ratio_plan_review',
            'reason': '旧排序按初始 final_priority 稳定降序；被动关系单独入列但比例基础系数为零。比例与归一化仅为审计计划，未更新透干余额。',
            'scope': '完整主动／被动记录的旧排序与受限比例计划；不执行分数分配。',
            'relationship_order': [{**row, 'rank': rank}
                                   for rank, row in enumerate(sorted_rows, 1)],
            'ratio_plan': normalized, 'priority_order': [
                {'rank': item['rank'], 'owner_pillar': item['owner_pillar'],
                 'other_pillar': item['other_pillar'], 'relation': item['relation']}
                for item in normalized],
            'allocations': None, 'totals_after': None}
