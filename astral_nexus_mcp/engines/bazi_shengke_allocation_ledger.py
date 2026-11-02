"""Restricted replay of the legacy allocation budget, before stem interactions."""
from math import isclose, isfinite

from astral_nexus_mcp.engines.bazi_shengke_allocation_plan import audit as audit_plan
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS

VERSION = 'bazi-shengke-allocation-ledger-1'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅重放分配预算扣减；原透干分数与五行汇总尚未改写。',
            'records': [], 'budget_balances_after': None,
            'visible_balances_after': None, 'totals_after': None}


def replay(pillars, branch_replay, five_he, reverse_pass, inputs, tongguan,
           zhihua, events, priority, plan):
    canonical = audit_plan(pillars, branch_replay, five_he, reverse_pass, inputs,
                           tongguan, zhihua, events, priority)
    if canonical['status'] != 'ratio_plan_review' or plan != canonical:
        return _stop('排序与比例计划未完整核对。')
    visible = {row['pillar']: row['score'] for row in reverse_pass['visible_balances_after']}
    if set(visible) != set(PILLARS) or any(not isfinite(score) or score <= 0
                                          for score in visible.values()):
        return _stop('前序透干余额缺失或非正。')
    balances = visible.copy()
    records = []
    for row in plan['ratio_plan']:
        owner, target = row['owner_pillar'], row['other_pillar']
        ratio = row['normalized_ratio']
        if owner not in visible or target not in visible or not 0 <= ratio <= 1:
            return _stop('分配比例或柱位无效。')
        before = balances[owner]
        # Legacy captures each owner's original available_score before any
        # deductions. Passive relations have a reviewed zero ratio.
        amount = visible[owner] * ratio
        if row['direction'] == 'active':
            balances[owner] -= amount
        elif row['direction'] == 'passive':
            if ratio != 0:
                return _stop('被动关系出现非零比例，超出已审旧行为。')
        else:
            return _stop('关系方向无效。')
        if balances[owner] < -1e-8 or not isfinite(balances[owner]):
            return _stop('分配预算透支或非有限值。')
        if abs(balances[owner]) < 1e-8:
            balances[owner] = 0.0
        records.append({'rank': row['rank'], 'owner_pillar': owner,
                        'other_pillar': target, 'relation': row['relation'],
                        'direction': row['direction'], 'ratio': ratio,
                        'budget_before': round(before, 6),
                        'budget_amount': round(amount, 6),
                        'budget_after': round(balances[owner], 6)})
    for owner in PILLARS:
        expected = visible[owner] * (1 - sum(row['normalized_ratio']
            for row in plan['ratio_plan'] if row['owner_pillar'] == owner and row['direction'] == 'active'))
        if not isclose(balances[owner], expected, abs_tol=1e-7):
            return _stop('同一透干预算与比例合计不一致。')
    return {'version': VERSION, 'status': 'budget_replay',
            'reason': '按旧排序逐条记录分配预算；后续生克循环仍读取作用前透干分数，预算余额不是阶段力量。',
            'scope': '仅重放分配预算扣减；原透干分数与五行汇总尚未改写。',
            'records': records,
            'budget_balances_after': [{'pillar': owner, 'stem': pillars[index]['stem'],
                                       'score': round(balances[owner], 6)}
                                      for index, owner in enumerate(PILLARS)],
            'visible_balances_after': None, 'totals_after': None}
