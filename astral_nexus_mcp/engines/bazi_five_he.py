"""Audited five-he gates and ordered stage-only score transfers."""
import json
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_branch_replay import _strength_status
from astral_nexus_mcp.engines.bazi_interactions import GENERATES, CONTROLS, MONTH_STATUS, PAIR_PRIORITY
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-five-he-audit-4'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_five_he_v1.json').read_text())
PILLAR_IDS = ('year', 'month', 'day', 'hour')


def _result(status, candidates, checks, reason, before=None, after=None, changes=None,
            applied_pairs=None, applied_pair_details=None):
    return {'version': VERSION, 'status': status, 'candidates': candidates,
            'checks': checks, 'reason': reason, 'totals_before': before,
            'totals_after': after, 'changes': changes or [],
            'applied_pairs': applied_pairs or [],
            'applied_pair_details': applied_pair_details or [],
            'scope': '逐对审核五合阶段和透干转移；不代表化气格或最终力量。'}


def _main_element(branch):
    stem = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items() if qi == '本气')
    return LunarUtil.WU_XING_GAN[stem]


def _candidate_pairs(pillars):
    candidates = []
    for left, right in PAIR_PRIORITY:
        pair = frozenset((pillars[left]['stem'], pillars[right]['stem']))
        for rule_key, rule in RULES['combos'].items():
            if pair == frozenset(rule_key):
                candidates.append({'rule_key': rule_key, 'pillars': [PILLAR_IDS[left], PILLAR_IDS[right]],
                                   'stems': [pillars[left]['stem'], pillars[right]['stem']],
                                   'target_element': rule['target_element'], 'distance': abs(left - right)})
    return candidates


def review(pillars: list[dict], branch_replay: dict):
    """Check candidates in legacy priority order and replay accepted transfers."""
    candidates = _candidate_pairs(pillars)
    if not candidates:
        return _result('no_candidate', [], [], '四透干没有五合配对。')
    if branch_replay['status'] not in ('isolated_pair_stages', 'isolated_group_branch_stage'):
        return _result('not_covered', candidates, [], '前序地支分数未完整复算，不能进入五合分数转移。')
    if len(candidates) > 1:
        # Legacy priority walks all pairs and only occupies stems after an
        # actual transfer. Rejected candidates cannot block a later pair.
        checks = []
        accepted = []
        occupied = set()
        stage_totals = branch_replay['totals_after'].copy()
        stem_scores = {p['id']: WEIGHT_RULES['stem_base_weight'][LunarUtil.WU_XING_GAN[p['stem']]]
                       for p in pillars}
        for candidate in candidates:
            if occupied.intersection(candidate['pillars']):
                checks.append({'id': 'occupied', 'passed': False,
                               'detail': '先行成功五合已占用参与干。',
                               'candidate_pillars': candidate['pillars']})
                continue
            single = _review_candidate(pillars, {**branch_replay, 'totals_after': stage_totals},
                                       candidate, stem_scores)
            checks.extend([dict(check, candidate_pillars=candidate['pillars'])
                           for check in single['checks']])
            if single['status'] in ('isolated_partial_stage', 'isolated_complete_stage'):
                accepted.append(single)
                occupied.update(candidate['pillars'])
                stage_totals = single['totals_after']
                for change in single['changes']:
                    stem_scores[change['from_pillar']] -= change['amount']
                    stem_scores[change['to_pillar']] += change['amount']
            elif single['status'] != 'guard_failed':
                return _result('not_covered', candidates, checks,
                               '多组五合候选出现未审核的作用结果。')
        if accepted:
            return _result('isolated_partial_stage' if any(
                row['status'] == 'isolated_partial_stage' for row in accepted)
                else 'isolated_complete_stage', candidates, checks,
                '按旧配对优先级逐对转移，成功关系占用参与干，后续关系读取更新余额。',
                branch_replay['totals_after'], stage_totals,
                [change for row in accepted for change in row['changes']],
                [pair for row in accepted for pair in row['applied_pairs']],
                [detail for row in accepted for detail in row['applied_pair_details']])
        return _result('guard_failed', candidates, checks,
                       '多组五合候选逐对核对，均被旧门槛阻止。')
    return _review_candidate(pillars, branch_replay, candidates[0])


def _review_candidate(pillars, branch_replay, candidate, stem_scores=None):
    candidates = [candidate]
    left, right = (PILLAR_IDS.index(name) for name in candidate['pillars'])
    target = candidate['target_element']
    totals = branch_replay['totals_after']
    checks = []

    def gate(name, passed, detail):
        checks.append({'id': name, 'passed': passed, 'detail': detail})
        return passed

    if not gate('distance', candidate['distance'] <= 2, f"柱距 {candidate['distance']}；仅相邻或隔一干可进入后续条件。"):
        return _result('guard_failed', candidates, checks, '五合距离条件不满足。')
    month_status = MONTH_STATUS[pillars[1]['branch']][target]
    if not gate('month_support', month_status in ('旺', '相'), f'{target}在{pillars[1]["branch"]}月为{month_status}。'):
        return _result('guard_failed', candidates, checks, '化神月令条件不满足。')
    exposed = [p['id'] for p in pillars if p['id'] != 'day' and LunarUtil.WU_XING_GAN[p['stem']] == target]
    if not gate('exposed', bool(exposed), f'非日柱透出化神五行：{exposed}。'):
        return _result('guard_failed', candidates, checks, '化神未在非日柱透出。')
    strength = _strength_status(target, totals)
    if not gate('target_strength', strength in ('强旺', '一般'), f'前序阶段{target}强弱门槛：{strength}。'):
        return _result('guard_failed', candidates, checks, '化神强弱门槛不满足。')
    if candidate['distance'] == 2:
        mid = min(left, right) + 1
        a, b = (LunarUtil.WU_XING_GAN[pillars[index]['stem']] for index in (left, right))
        middle = LunarUtil.WU_XING_GAN[pillars[mid]['stem']]
        ends_control = CONTROLS[a] == b or CONTROLS[b] == a
        chain = ((GENERATES[a] == middle and GENERATES[middle] == b)
                 or (GENERATES[b] == middle and GENERATES[middle] == a))
        if not gate('separated_chain', ends_control and chain,
                    f'隔干{pillars[mid]["stem"]}：两端相克={ends_control}，双步相生={chain}。'):
            return _result('guard_failed', candidates, checks, '隔干通关条件不满足。')
    non_target_indices = [index for index in (left, right)
                          if LunarUtil.WU_XING_GAN[pillars[index]['stem']] != target]
    share = totals[target] / sum(totals.values())
    competitors = [pillars[index]['stem'] for index in non_target_indices
                   if sum(p['stem'] == pillars[index]['stem'] for p in pillars) > 1]
    if not gate('competition', not competitors or share > .5,
                f'非化神方同干争合={competitors}；化神前序占比={share:.4f}。'):
        return _result('guard_failed', candidates, checks, '争合条件阻止分数转移。')
    partial_reasons = []
    killer_indices = [index for index, pillar in enumerate(pillars)
                      if index not in (left, right) and pillar['stem'] not in candidate['stems']
                      and pillar['stem'] in RULES['killer_stems'][target]]
    eligible_killers = []
    for index in killer_indices:
        killer = pillars[index]['stem']
        rooted = any(killer in LunarUtil.ZHI_HIDE_GAN[p['branch']] for p in pillars)
        base_support = GENERATES[_main_element(pillars[index]['branch'])] == LunarUtil.WU_XING_GAN[killer]
        if rooted or base_support:
            gate('third_party_killer', False, f'{killer}有根={rooted}，坐支本气生其五行={base_support}。')
            return _result('guard_failed', candidates, checks, '第三方破合干有根或得坐支本气生扶。')
        official = RULES['official_for_killer'][killer]
        adjacent_official = any(abs(index - other) == 1 and p['stem'] == official
                                for other, p in enumerate(pillars))
        if not adjacent_official:
            eligible_killers.append(killer)
    if not gate('third_party_killer', len(eligible_killers) <= 1,
                f'无根且无贴身制约的第三方破合干：{eligible_killers}。'):
        return _result('guard_failed', candidates, checks, '第三方破合干超过一个。')
    if eligible_killers:
        partial_reasons.append('第三方破合干' + eligible_killers[0])
    for index in non_target_indices:
        element = LunarUtil.WU_XING_GAN[pillars[index]['stem']]
        base = _main_element(pillars[index]['branch'])
        if not gate('sitting_support', GENERATES[base] != element,
                    f'{PILLAR_IDS[index]}柱坐支本气{base}，非化神方属{element}。'):
            return _result('guard_failed', candidates, checks, '非化神方坐支本气生扶，阻止转移。')
        roots = [(p['id'], stem, WEIGHT_RULES['branch_qi_type'][p['branch']][stem])
                 for p in pillars for stem in LunarUtil.ZHI_HIDE_GAN[p['branch']]
                 if LunarUtil.WU_XING_GAN[stem] == element]
        main_roots = [root for root in roots if root[2] == '本气']
        if not gate('non_target_roots', not main_roots and len(roots) <= 1,
                    f'{PILLAR_IDS[index]}柱非化神方同五行根：{roots}。'):
            return _result('guard_failed', candidates, checks, '非化神方本气根或多个根阻止转移。')
        if roots:
            partial_reasons.append('非化神方单一非本气根')
        producers = [p['stem'] for p in pillars if GENERATES[LunarUtil.WU_XING_GAN[p['stem']]] == element]
        if producers:
            partial_reasons.append('透干生非化神方' + producers[0])
    if not gate('partial_reason_count', len(partial_reasons) <= 1, f'部分作用理由：{partial_reasons}。'):
        return _result('guard_failed', candidates, checks, '多个部分作用理由叠加，旧门槛阻止合化。')
    receiver_indices = [index for index in (left, right)
                        if LunarUtil.WU_XING_GAN[pillars[index]['stem']] == target]
    if not receiver_indices:
        receiver_indices = [index for index, p in enumerate(pillars)
                            if LunarUtil.WU_XING_GAN[p['stem']] == target]
    if not receiver_indices:
        return _result('not_covered', candidates, checks, '化神透干接收方缺失。')
    coeff = (1.2 if strength == '强旺' else 1.0)
    ratio_factor = ((.4 + (coeff - .8) * .5) if partial_reasons else coeff) * (
        1.0 if candidate['distance'] == 1 else .7)
    # The old partial formula halves again for a third-party killer (争合)
    # or a single non-main root (破合). These are independent gate flags.
    if any(reason.startswith('第三方破合干') for reason in partial_reasons):
        ratio_factor *= .5
    if '非化神方单一非本气根' in partial_reasons:
        ratio_factor *= .5
    after = totals.copy()
    changes = []
    for donor in non_target_indices:
        donor_stem = pillars[donor]['stem']
        donor_element = LunarUtil.WU_XING_GAN[donor_stem]
        donor_before = (stem_scores[PILLAR_IDS[donor]] if stem_scores is not None else
                        WEIGHT_RULES['stem_base_weight'][donor_element])
        adjustment = RULES['combos'][candidate['rule_key']]['stem_adjustments'][donor_stem]
        # Legacy complete conversion uses the raw reduction; partial applies
        # the reviewed ratio, then credits exposed target stems equally.
        transfer = -donor_before * adjustment * (ratio_factor if partial_reasons else 1.0)
        after[donor_element] = round(after[donor_element] - transfer, 6)
        for receiver in receiver_indices:
            amount = transfer / len(receiver_indices)
            after[target] = round(after[target] + amount, 6)
            changes.append({'from_pillar': PILLAR_IDS[donor], 'from_stem': donor_stem,
                            'to_pillar': PILLAR_IDS[receiver], 'to_stem': pillars[receiver]['stem'],
                            'ratio_factor': round(ratio_factor, 6), 'amount': round(amount, 6),
                            'reason': partial_reasons[0] if partial_reasons else '无阻断或部分作用理由'})
    return _result('isolated_partial_stage' if partial_reasons else 'isolated_complete_stage',
                   candidates, checks,
                   ('单一部分作用理由下的五合阶段分数转移；不判定化气格。' if partial_reasons else
                    '无部分作用理由，按旧完全五合路径转移；记录的比例系数不乘入捐出量；不判定化气格。'),
                   totals, after, changes, [candidate['pillars']],
                   [{'pillars': candidate['pillars'],
                     'grade': '部分合化' if partial_reasons else '完全合化',
                     'reasons': partial_reasons}])
