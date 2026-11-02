"""First eligible visible-stem interaction after the reviewed budget replay."""
from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_allocation_ledger import replay as replay_ledger
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS
from astral_nexus_mcp.engines.bazi_shengke_visible_rules import calculate as calculate_visible
from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES

VERSION = 'bazi-shengke-visible-probe-3'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅排序后首条已审透干生克关系的局部作用；其余关系与阶段总分未复算。',
            'operation': None, 'remaining_relationships': None,
            'visible_balances_after': None, 'totals_after': None}


def replay(pillars, branch_replay, five_he, reverse_pass, inputs, tongguan,
           zhihua, events, priority, plan, ledger):
    canonical = replay_ledger(pillars, branch_replay, five_he, reverse_pass, inputs,
                              tongguan, zhihua, events, priority, plan)
    if canonical['status'] != 'budget_replay' or ledger != canonical:
        return _stop('分配预算未完整核对。')
    first = ratio_row = None
    for candidate, candidate_ratio in zip(plan['relationship_order'], plan['ratio_plan']):
        if candidate['direction'] == 'active':
            first, ratio_row = candidate, candidate_ratio
            break
        actor_stem = pillars[PILLARS.index(candidate['owner_pillar'])]['stem']
        target_stem = pillars[PILLARS.index(candidate['other_pillar'])]['stem']
        actor_element = LunarUtil.WU_XING_GAN[actor_stem]
        target_element = LunarUtil.WU_XING_GAN[target_stem]
        if (candidate_ratio['direction'] != 'passive' or
                candidate_ratio['normalized_ratio'] != 0 or
                GENERATES[actor_element] == target_element or
                CONTROLS[actor_element] == target_element):
            return _stop('前置被动镜像可能作用，尚未覆盖。')
    if first is None or first['relation'] not in ('生', '克'):
        return _stop('排序中没有已审主动生克关系。')
    actor, target = first['owner_pillar'], first['other_pillar']
    if (ratio_row['normalized_ratio'] < .1 or
            (ratio_row['owner_pillar'], ratio_row['other_pillar']) != (actor, target)):
        return _stop('首条关系比例不足或与排序不一致。')
    key = (actor, target)
    control = next(row['control'] for row in zhihua['relationships']
                   if (row['actor_pillar'], row['target_pillar']) == key)
    drain = next(row['drain'] for row in zhihua['relationships']
                 if (row['actor_pillar'], row['target_pillar']) == key)
    path = next(row['path'] for row in tongguan['paths']
                if (row['actor_pillar'], row['target_pillar']) == key)
    event = next(row['event_link'] for row in events['relationships']
                 if (row['actor_pillar'], row['target_pillar']) == key)
    if control['status'] != 'none' or drain['status'] != 'none' or path or event:
        return _stop('首条关系含尚未纳入单步作用的制化、通关或五合状态。')
    visible = {row['pillar']: row['score'] for row in reverse_pass['visible_balances_after']}
    actor_before, target_before = visible[actor], visible[target]
    allocated_actor = actor_before * ratio_row['normalized_ratio']
    actor_stem = pillars[PILLARS.index(actor)]['stem']
    target_stem = pillars[PILLARS.index(target)]['stem']
    actor_element = LunarUtil.WU_XING_GAN[actor_stem]
    target_element = LunarUtil.WU_XING_GAN[target_stem]
    totals = reverse_pass['totals_after']
    if target_before <= 0 or totals[target_element] <= 0 or allocated_actor <= 0:
        return _stop('首条关系的目标余额或分母非正。')
    global_ratio = totals[actor_element] / totals[target_element]
    current_ratio = allocated_actor / target_before
    actor_root = any(row['element'] == actor_element and row['score'] > 0
                     for row in reverse_pass['hidden_balances_after'])
    target_root = any(row['element'] == target_element and row['score'] > 0
                      for row in reverse_pass['hidden_balances_after'])
    operation = calculate_visible(allocated_actor, target_before, global_ratio,
                                  current_ratio, first['relation'], actor_stem,
                                  target_stem, actor_root, target_root)
    if operation is None:
        return _stop('首条关系分数或比值无效。')
    level, delta = operation['level'], operation['delta']
    actor_change, target_change = operation['actor_change'], operation['target_change']
    return {'version': VERSION, 'status': 'isolated_first_visible_operation',
            'reason': '按旧第三段首条关系使用原透干余额与归一化比例，在已审等级内计算单步变化。',
            'scope': '仅排序后首条已审透干生克关系的局部作用；其余关系与阶段总分未复算。',
            'operation': {'rank': ratio_row['rank'], 'actor_pillar': actor, 'actor_stem': actor_stem,
                          'target_pillar': target, 'target_stem': target_stem,
                          'relation': first['relation'], 'level': level,
                          'polarity_coefficient': operation['polarity_coefficient'],
                          'actor_has_root': actor_root, 'target_has_root': target_root,
                          'normalized_ratio': ratio_row['normalized_ratio'],
                          'allocated_actor': round(allocated_actor, 6),
                          'ratio_global': round(global_ratio, 6),
                          'ratio_current': round(current_ratio, 6),
                          'base_delta': round(delta, 6),
                          'actor_before': round(actor_before, 6),
                          'actor_change': round(actor_change, 6),
                          'actor_after': round(actor_before + actor_change, 6),
                          'target_before': round(target_before, 6),
                          'target_change': round(target_change, 6),
                          'target_after': round(target_before + target_change, 6)},
            'remaining_relationships': len(plan['relationship_order']) - ratio_row['rank'],
            'visible_balances_after': None, 'totals_after': None}
