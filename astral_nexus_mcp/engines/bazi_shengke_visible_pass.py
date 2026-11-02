"""Restricted complete visible-stem pass after the reviewed allocation budget."""
from collections import Counter
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS
from astral_nexus_mcp.engines.bazi_shengke_visible_probe import replay as replay_probe
from astral_nexus_mcp.engines.bazi_shengke_visible_rules import calculate as calculate_visible

VERSION = 'bazi-shengke-visible-pass-3'


def _stop(reason, rank=None):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '已核对等级的透干顺序作用；环境压制及最终力量未计算。',
            'stopped_at_rank': rank, 'events': [], 'blocked': [], 'skipped': [],
            'visible_balances_after': None, 'hidden_balances_after': None,
            'totals_before': None, 'totals_after': None}


def replay(pillars, branch_replay, five_he, reverse_pass, inputs, tongguan,
           zhihua, events, priority, plan, ledger, probe):
    canonical = replay_probe(pillars, branch_replay, five_he, reverse_pass, inputs,
                             tongguan, zhihua, events, priority, plan, ledger)
    if probe != canonical or ledger.get('status') != 'budget_replay':
        return _stop('首条透干作用未完整核对。')
    visible = {row['pillar']: row['score'] for row in reverse_pass['visible_balances_after']}
    hidden = reverse_pass['hidden_balances_after']
    totals = Counter()
    for row in reverse_pass['visible_balances_after'] + hidden:
        totals[row['element']] += row['score']
    if any(not isclose(totals[e], reverse_pass['totals_after'][e], abs_tol=.000002)
           for e in '木火土金水'):
        return _stop('前序逐干余额与汇总不一致。')
    before = {e: round(totals[e], 6) for e in '木火土金水'}
    zh_by_pair = {(row['actor_pillar'], row['target_pillar']): row
                  for row in zhihua['relationships']}
    path_by_pair = {(row['actor_pillar'], row['target_pillar']): row['path']
                    for row in tongguan['paths']}
    event_by_pair = {(row['actor_pillar'], row['target_pillar']): row['event_link']
                     for row in events['relationships']}
    operations, blocked, skipped = [], [], []
    for row in plan['ratio_plan']:
        rank, actor, target = row['rank'], row['owner_pillar'], row['other_pillar']
        actor_stem = pillars[PILLARS.index(actor)]['stem']
        target_stem = pillars[PILLARS.index(target)]['stem']
        actor_element = LunarUtil.WU_XING_GAN[actor_stem]
        target_element = LunarUtil.WU_XING_GAN[target_stem]
        if visible[target] <= 0 or totals[target_element] <= 0:
            return _stop('目标透干余额或五行分母非正，不能继续顺序作用。', rank)
        if row['direction'] == 'passive':
            if (GENERATES[actor_element] == target_element or
                    CONTROLS[actor_element] == target_element):
                return _stop('被动镜像记录意外形成反向生克，当前边界未覆盖。', rank)
            skipped.append({'rank': rank, 'owner_pillar': actor,
                            'other_pillar': target, 'reason': '被动镜像无反向生克作用。'})
            continue
        relation = ('生' if GENERATES[actor_element] == target_element else
                    '克' if CONTROLS[actor_element] == target_element else None)
        if relation != row['relation']:
            return _stop('主动关系与透干五行不一致。', rank)
        pair = actor, target
        control = zh_by_pair[pair]['control']
        drain = zh_by_pair[pair]['drain']
        path = path_by_pair[pair]
        event = event_by_pair[pair]
        ratio = row['normalized_ratio']
        if ratio < .1:
            reason = ('五合事件低分方' if event and not event['actor_is_higher'] else
                      '完全受制' if control['status'] == 'full' else
                      '完全被化泄' if drain['status'] == 'full' else
                      '完全通关' if path and path['status'] == 'full' else
                      '作用比例不足')
            blocked.append({'rank': rank, 'actor_pillar': actor,
                            'target_pillar': target, 'relation': relation,
                            'ratio': ratio, 'legacy_block_reason': reason})
            continue
        # 制化、五合和非完全通关已由前序旧优先级及分配比例纳入。
        # 旧第三段只有「完全通关的克」改用生的数值表；其他正比例
        # 关系仍按其本来的生克关系作用。
        allocated = visible[actor] * ratio
        global_ratio = totals[actor_element] / totals[target_element]
        current_ratio = allocated / visible[target]
        actor_root = any(item['element'] == actor_element and item['score'] > 0 for item in hidden)
        target_root = any(item['element'] == target_element and item['score'] > 0 for item in hidden)
        mediated = relation == '克' and path and path['status'] == 'full'
        if mediated:
            middle = path['middle_pillar']
            middle_stem = pillars[PILLARS.index(middle)]['stem']
            middle_element = LunarUtil.WU_XING_GAN[middle_stem]
            middle_score = visible[middle]
            operation = calculate_visible(
                allocated, middle_score, totals[actor_element] / totals[middle_element],
                middle_score / totals[actor_element], '生', actor_stem, middle_stem,
                actor_root, any(item['element'] == middle_element and item['score'] > 0
                                for item in hidden))
        else:
            operation = calculate_visible(allocated, visible[target], global_ratio,
                                          current_ratio, relation, actor_stem, target_stem,
                                          actor_root, target_root)
        if operation is None:
            return _stop('正比例关系分数或比值无效。', rank)
        level, delta = operation['level'], operation['delta']
        actor_change, target_change = operation['actor_change'], operation['target_change']
        if delta == 0:
            skipped.append({'rank': rank, 'owner_pillar': actor,
                            'other_pillar': target, 'reason': '旧配置判定' +
                            ('通关／' if mediated else '') + level + '，无变化。'})
            continue
        actor_before, target_before = visible[actor], visible[target]
        visible[actor] += actor_change
        visible[target] += target_change
        totals[actor_element] += actor_change
        totals[target_element] += target_change
        if any(not isfinite(score) or score < 0 for score in visible.values()):
            return _stop('透干作用后余额无效。', rank)
        operations.append({'rank': rank, 'actor_pillar': actor, 'actor_stem': actor_stem,
                           'target_pillar': target, 'target_stem': target_stem,
                           'relation': relation, 'level': '通关' if mediated else level,
                           'numeric_level': level, 'mediated_by': middle if mediated else None,
                           'polarity_coefficient': operation['polarity_coefficient'],
                           'normalized_ratio': ratio,
                           'allocated_actor': round(allocated, 6),
                           'ratio_global': round(global_ratio, 6),
                           'ratio_current': round(current_ratio, 6),
                           'base_delta': round(delta, 6),
                           'actor_before': round(actor_before, 6),
                           'actor_change': round(actor_change, 6),
                           'actor_after': round(visible[actor], 6),
                           'target_before': round(target_before, 6),
                           'target_change': round(target_change, 6),
                           'target_after': round(visible[target], 6)})
    first_operation = probe.get('operation')
    if first_operation and first_operation['base_delta'] == 0:
        if not any(item['rank'] == first_operation['rank'] and '无变化' in item['reason']
                   for item in skipped):
            return _stop('首条无变化关系与已审探针不一致。')
    elif first_operation and (not operations or any(operations[0][key] != first_operation[key]
                               for key in ('actor_pillar', 'target_pillar', 'base_delta',
                                           'actor_after', 'target_after'))):
        return _stop('首条作用与已审局部探针不一致。')
    reconciled = Counter()
    for index, owner in enumerate(PILLARS):
        reconciled[LunarUtil.WU_XING_GAN[pillars[index]['stem']]] += visible[owner]
    for item in hidden:
        reconciled[item['element']] += item['score']
    if any(not isclose(totals[e], reconciled[e], abs_tol=.000002) for e in '木火土金水'):
        return _stop('透干阶段逐干余额与五行汇总不一致。')
    return {'version': VERSION, 'status': 'isolated_visible_pass',
            'reason': '排序关系已逐项复核；正比例且落在已审等级内的作用、镜像与阻止项明列。',
            'scope': '已核对等级的透干顺序作用；环境压制及最终力量未计算。',
            'stopped_at_rank': None, 'events': operations, 'blocked': blocked,
            'skipped': skipped,
            'visible_balances_after': [dict(item, score=visible[item['pillar']])
                                       for item in reverse_pass['visible_balances_after']],
            'hidden_balances_after': hidden,
            'totals_before': before,
            'totals_after': {e: round(totals[e], 6) for e in '木火土金水'}}
