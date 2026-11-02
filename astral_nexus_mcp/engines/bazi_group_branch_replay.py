"""Close the branch stage when one reviewed group has no later numeric effects."""

from astral_nexus_mcp.engines.bazi_group_probe import audit as audit_group, replay as replay_group
from astral_nexus_mcp.engines.bazi_branch_replay import _apply_void
from astral_nexus_mcp.engines.bazi_interactions import audit as audit_interactions
from astral_nexus_mcp.engines.bazi_kongwang import audit as audit_kongwang
from astral_nexus_mcp.engines.bazi_strength import calculate_partial

VERSION = 'bazi-group-branch-replay-2'
ZERO_KINDS = {'liuhe', 'banhe', 'xing', 'gonghe'}


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'events': [], 'skipped': [], 'kongwang_events': [],
            'hidden_balances': None, 'totals_before': None,
            'totals_after': None}


def replay(pillars, partial, interactions, group_audit, group_probe):
    """Return a stage total only if every event after the group is proven inert."""
    try:
        if partial != calculate_partial(pillars):
            return _stop('初始权重与四柱不一致。')
        canonical_interactions = audit_interactions(pillars, partial)
        if interactions != canonical_interactions:
            return _stop('地支关系输入与四柱不一致。')
        canonical_audit = audit_group(pillars, partial, interactions)
        if group_audit != canonical_audit or canonical_audit['status'] != 'single_group_review':
            return _stop('唯一三会／三合组尚未完整核对。')
        canonical_probe = replay_group(pillars, partial, interactions, group_audit)
        if group_probe != canonical_probe or canonical_probe['status'] != 'isolated_first_group':
            return _stop('单组藏干复算尚未完整核对。')
        kongwang = audit_kongwang(pillars, interactions)
        if kongwang['status'] != 'audited':
            return _stop('会合后的旬空审核无法核对。')
        first = group_audit['first_group']
        events = interactions['branch_events']
        matches = [event for event in events if event['kind'] == first['kind']
                   and event['rule_key'] == first['rule_key']]
        if len(matches) != 1 or set(matches[0]['pillars']) != set(first['positions']):
            return _stop('三会／三合事件与单组审核不一致。')
        skipped = []
        occupied = set(first['positions']) if first['legacy_group_grade'] == '完全' else set()
        for event in events:
            if event is matches[0]:
                continue
            if (event['kind'] in ('liuhe', 'banhe', 'gonghe') and
                    occupied.intersection(event['pillars'])):
                skipped.append({'kind': event['kind'], 'rule_key': event['rule_key'],
                                'pillars': event['pillars'],
                                'reason': '先行完全会合组占用参与支'})
                continue
            if (event['kind'] not in ZERO_KINDS or
                    event['condition_review'].get('grade_if_reached') != 'none_if_reached'):
                return _stop('存在后续可能生效的地支关系，尚未复算占用和顺序作用。')
            skipped.append({'kind': event['kind'], 'rule_key': event['rule_key'],
                            'pillars': event['pillars'],
                            'reason': '不满足结构作用条件；本阶段分数不变'})
        scores = {p['id']: {element: 0.0 for element in '木火土金水'} for p in pillars}
        for row in group_probe['hidden_balances_after']:
            scores[row['pillar']][row['element']] += row['score']
        totals = dict(group_probe['totals_after'])
        kongwang_events = _apply_void(pillars, kongwang['positions'], scores, totals, occupied)
        if kongwang_events is None:
            return _stop('完全会合后的重复旬空支占用归属不明。')
        hidden = [{'pillar': row['pillar'], 'branch': row['branch'],
                   'stem': row['stem'], 'element': row['element'],
                   'qi': row['qi'], 'score': scores[row['pillar']][row['element']]}
                  for row in group_probe['hidden_balances_after']]
        grade = first['legacy_group_grade'] + ('三会' if first['kind'] == 'sanhui' else '三合')
        return {'version': VERSION, 'status': 'isolated_group_branch_stage',
                'reason': '唯一三会／三合组已复算，后续关系依实际占用跳过或结构零作用；旬空已逐支核对。',
                'group': {'kind': first['kind'], 'rule_key': first['rule_key'],
                          'positions': first['positions']},
                'events': [{'kind': first['kind'], 'rule_key': first['rule_key'],
                            'pillars': first['positions'], 'grade': grade}],
                'skipped': skipped, 'kongwang_events': kongwang_events,
                'hidden_balances': hidden,
                'totals_before': partial['totals_before'],
                'totals_after': {element: round(totals[element], 6) for element in '木火土金水'}}
    except (KeyError, TypeError, ValueError):
        return _stop('地支阶段输入缺失或无效。')
