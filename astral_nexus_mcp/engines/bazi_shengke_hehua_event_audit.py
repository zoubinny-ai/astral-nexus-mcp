"""Map a reviewed five-he transfer to legacy third-pass event flags."""
from astral_nexus_mcp.engines.bazi_five_he import review as review_five_he
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS, audit as audit_inputs
from astral_nexus_mcp.engines.bazi_shengke_tongguan_audit import audit as audit_tongguan
from astral_nexus_mcp.engines.bazi_shengke_zhihua_audit import audit as audit_zhihua

VERSION = 'bazi-shengke-hehua-event-audit-3'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅把已核对的五合阶段双方转移映射为旧生克第三段的事件关联；不判化格。',
            'event_pair': None, 'event_pairs': [], 'relationships': [], 'priority_order': None,
            'allocations': None, 'totals_after': None}


def audit(pillars: list[dict], branch_replay: dict, five_he: dict,
          reverse_pass: dict, priority_inputs: dict, tongguan: dict, zhihua: dict):
    try:
        canonical_five_he = review_five_he(pillars, branch_replay)
    except (KeyError, TypeError, ValueError):
        return _stop('五合阶段前序地支证据缺失或无法核对。')
    if canonical_five_he != five_he or five_he['status'] not in (
            'isolated_partial_stage', 'isolated_complete_stage', 'no_candidate', 'guard_failed'):
        return _stop('五合阶段未覆盖或与前序地支证据不一致。')
    if (five_he['status'] == 'guard_failed' and
            (not five_he['candidates'] or not five_he['checks'] or
             all(check['passed'] for check in five_he['checks']) or five_he['changes'])):
        return _stop('五合门槛失败状态缺少唯一候选或出现未审核的转移。')
    canonical_inputs = audit_inputs(pillars, reverse_pass)
    if canonical_inputs['status'] != 'inputs_only' or priority_inputs != canonical_inputs:
        return _stop('前序透干关系输入未完整覆盖。')
    canonical_tongguan = audit_tongguan(pillars, reverse_pass, canonical_inputs)
    if canonical_tongguan['status'] != 'structural_review' or tongguan != canonical_tongguan:
        return _stop('前序通关路径与关系输入不一致。')
    canonical_zhihua = audit_zhihua(pillars, reverse_pass, canonical_inputs, canonical_tongguan)
    if canonical_zhihua['status'] != 'structural_review' or zhihua != canonical_zhihua:
        return _stop('前序制／化状态与关系输入不一致。')
    event_pairs = []
    if five_he['status'] in ('isolated_partial_stage', 'isolated_complete_stage'):
        changes = five_he['changes']
        candidates = five_he['candidates']
        pairs = five_he.get('applied_pairs', [])
        if not pairs or not changes:
            return _stop('受限五合事件没有参与双方或数值转移。')
        visible = {(row['pillar'], row['stem']): row['score']
                   for row in reverse_pass['visible_balances_after']}
        for pair in pairs:
            candidate = next((row for row in candidates if row['pillars'] == pair), None)
            if candidate is None:
                return _stop('五合转移双方不在候选关系中。')
            pair_changes = [change for change in changes if change['from_pillar'] in pair]
            if not pair_changes or any(
                    change['amount'] <= 0 or
                    change['from_stem'] != pillars[PILLARS.index(change['from_pillar'])]['stem'] or
                    change['to_stem'] != pillars[PILLARS.index(change['to_pillar'])]['stem']
                    for change in pair_changes):
                return _stop('五合转移来源或接收方与四柱不一致。')
            left, right = pair
            left_score = visible[(left, pillars[PILLARS.index(left)]['stem'])]
            right_score = visible[(right, pillars[PILLARS.index(right)]['stem'])]
            if min(left_score, right_score) <= 0:
                return _stop('事件双方当前透干余额非正，不能计算比例。')
            higher, lower = (left, right) if left_score > right_score else (right, left)
            higher_score, lower_score = (left_score, right_score) if left_score > right_score else (right_score, left_score)
            event_pairs.append({'pillars': [left, right],
                                'stems': [pillars[PILLARS.index(left)]['stem'],
                                          pillars[PILLARS.index(right)]['stem']],
                                'transfer_amount': round(sum(change['amount'] for change in pair_changes), 6),
                                'higher_pillar': higher, 'higher_before': round(higher_score, 6),
                                'lower_pillar': lower, 'lower_before': round(lower_score, 6),
                                'ratio': round(higher_score / lower_score, 6),
                                'meaning': (('已核对的单一部分五合转移记录；仅对应旧事件关联条件。'
                                             if five_he['status'] == 'isolated_partial_stage' else
                                             '已核对的单一完全五合转移记录；仅对应旧事件关联条件。')
                                            if len(pairs) == 1 else
                                            '已核对多组五合中的一组转移记录；仅对应旧事件关联条件。')})
    relationships = []
    for row in canonical_inputs['relationships']:
        actor, target = row['actor_pillar'], row['target_pillar']
        pair = next((item for item in event_pairs if actor in item['pillars']), None)
        if pair:
            partner = next(p for p in pair['pillars'] if p != actor)
            link = {'kind': 'direct' if target == partner else 'indirect',
                    'partner_pillar': partner, 'actor_is_higher': actor == pair['higher_pillar']}
        else:
            link = None
        relationships.append({'actor_pillar': actor, 'target_pillar': target,
                              'relation': row['relation'], 'event_link': link})
    return {'version': VERSION, 'status': 'event_link_review',
            'reason': ('五合候选均被已审门槛阻止，本阶段无五合转移事件。'
                       if five_he['status'] == 'guard_failed' else
                       '已核对五合双方事件关联及作用前高低分；未把它解释为化格判定。'),
            'scope': '仅把已核对的五合阶段双方转移映射为旧生克第三段的事件关联；不判化格。',
            'event_pair': event_pairs[0] if len(event_pairs) == 1 else None,
            'event_pairs': event_pairs, 'relationships': relationships,
            'priority_order': None, 'allocations': None, 'totals_after': None}
