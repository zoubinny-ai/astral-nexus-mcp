"""Audit which hidden stems a reviewed group event activates for sheng-ke."""

from collections import Counter
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_group_branch_replay import replay as replay_group_branch
from astral_nexus_mcp.engines.bazi_group_probe import audit as audit_group, replay as replay_group
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES
from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES, RULES as SHENGKE_RULES, YANG, probe as probe_main
from astral_nexus_mcp.engines.bazi_shengke_first_pass import replay as replay_main_pass

VERSION = 'bazi-group-activation-1'
ELEMENT_ORDER = ('金', '木', '水', '火', '土')


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'rows': [], 'activated_non_main': [], 'first_pass_totals': None}


def audit(pillars, partial, interactions, group_audit, group_probe, group_branch):
    try:
        canonical_audit = audit_group(pillars, partial, interactions)
        canonical_probe = replay_group(pillars, partial, interactions, canonical_audit)
        canonical_branch = replay_group_branch(
            pillars, partial, interactions, canonical_audit, canonical_probe)
        if (group_audit != canonical_audit or group_probe != canonical_probe or
                group_branch != canonical_branch or
                canonical_branch['status'] != 'isolated_group_branch_stage'):
            return _stop('会合事件及完整地支阶段未核对。')
        target = group_audit['first_group']['target_element']
        receivers = {(row['pillar'], row['stem']) for row in group_probe['received']}
        converted = {(row['pillar'], row['stem']) for row in group_probe['converted']}
        rows = []
        for pillar in pillars:
            branch = pillar['branch']
            for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items():
                element = LunarUtil.WU_XING_GAN[stem]
                key = (pillar['id'], stem)
                if qi == '本气':
                    status, reason = 'active_main', '本气始终激活'
                elif key in receivers and element == target:
                    status, reason = 'active_group_target', '同一会合事件的化神藏干接收项'
                elif key in converted:
                    status, reason = 'inactive_mismatch', '参与转出，但藏干五行与化神不同'
                else:
                    status, reason = 'inactive_no_event_target', '没有匹配此藏干的会合事件记录'
                rows.append({'pillar': pillar['id'], 'branch': branch, 'stem': stem,
                             'qi': qi, 'element': element, 'status': status,
                             'reason': reason})
        return {'version': VERSION, 'status': 'audited',
                'reason': '按旧事件目标与受影响五行双条件审核非本气激活；未执行生克。',
                'group': group_branch['group'], 'target_element': target,
                'rows': rows,
                'activated_non_main': [row for row in rows
                                       if row['status'] == 'active_group_target'],
                'first_pass_totals': None}
    except (KeyError, TypeError, ValueError):
        return _stop('会合激活输入缺失或无效。')


def first_main_probe(pillars, activation, tonggen):
    """Use the existing main-qi probe only when no earlier active slot can act."""
    if activation.get('status') != 'audited' or tonggen.get('status') != 'isolated_tonggen_stage':
        return {'version': 'bazi-group-first-probe-1', 'status': 'not_covered',
                'reason': '会合激活或通根阶段未完整核对。', 'inputs': None,
                'first_operation': None, 'totals_after': None}
    day = pillars[2]
    actor_element = LunarUtil.WU_XING_GAN[day['stem']]
    main = next(stem for stem, qi in WEIGHT_RULES['branch_qi_type'][day['branch']].items()
                if qi == '本气')
    main_element = LunarUtil.WU_XING_GAN[main]
    for row in activation['rows']:
        if row['pillar'] != 'day' or row['status'] != 'active_group_target':
            continue
        if (ELEMENT_ORDER.index(row['element']) < ELEMENT_ORDER.index(main_element) and
                (GENERATES[actor_element] == row['element'] or
                 CONTROLS[actor_element] == row['element'])):
            return {'version': 'bazi-group-first-probe-1', 'status': 'not_covered',
                    'reason': '旧五行遍历顺序中，已激活非本气先于本气；数值规则尚未审核。',
                    'inputs': None, 'first_operation': None, 'totals_after': None}
    return probe_main(pillars, tonggen)


def first_pass(pillars, activation, tonggen):
    """Replay a single active non-main control relation in the legacy slot order."""
    stopped = {'version': 'bazi-group-first-pass-2', 'status': 'not_covered',
               'reason': '会合后的非本气作用尚未覆盖。', 'events': [], 'skipped': [],
               'visible_balances_after': None, 'hidden_balances_after': None,
               'totals_before': None, 'totals_after': None}
    if activation.get('status') != 'audited' or tonggen.get('status') != 'isolated_tonggen_stage':
        return {**stopped, 'reason': '会合激活或通根阶段未完整核对。'}
    active_relations = []
    for row in activation['activated_non_main']:
        actor = next(p['stem'] for p in pillars if p['id'] == row['pillar'])
        actor_element = LunarUtil.WU_XING_GAN[actor]
        if GENERATES[actor_element] == row['element'] or CONTROLS[actor_element] == row['element']:
            active_relations.append(row)
    if not active_relations:
        return replay_main_pass(pillars, tonggen)
    if len(active_relations) != 1 or CONTROLS[LunarUtil.WU_XING_GAN[next(
            p['stem'] for p in pillars if p['id'] == active_relations[0]['pillar'])]] != active_relations[0]['element']:
        return {**stopped, 'reason': '只覆盖唯一已激活非本气的透干克藏干作用。'}
    checked = probe_main(pillars, tonggen)
    if (checked['status'] != 'isolated_first_operation' and
            checked.get('reason') != '首个日柱本气无已审核的透干生克关系；其余关系尚未审核。'):
        return {**stopped, 'reason': '前序逐干余额或日柱输入未完整核对。'}
    visible_rows = tonggen['visible_balances_after']
    hidden_rows = tonggen['hidden_balances_after']
    try:
        row_keys = {(row['pillar'], row['stem']) for row in hidden_rows}
        audited = {(row['pillar'], row['stem']): row for row in activation['rows']}
        if (len(audited) != len(hidden_rows) or set(audited) != row_keys or
                activation['activated_non_main'] != [row for row in activation['rows']
                    if row['status'] == 'active_group_target'] or
                any(row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                    row['branch'] != next(p['branch'] for p in pillars if p['id'] == row['pillar']) or
                    row['qi'] != WEIGHT_RULES['branch_qi_type'][row['branch']][row['stem']]
                    or (row['status'] == 'active_main') != (row['qi'] == '本气') or
                    (row['status'] == 'active_group_target' and
                     (row['element'] != activation['target_element'] or
                      row['pillar'] not in activation['group']['positions']))
                    for row in activation['rows'])):
            return {**stopped, 'reason': '会合激活对象与逐藏干余额不一致。'}
        visible = {(row['pillar'], row['stem']): row['score'] for row in visible_rows}
        hidden = {(row['pillar'], row['stem']): row['score'] for row in hidden_rows}
        totals = Counter()
        for row in visible_rows + hidden_rows:
            totals[row['element']] += row['score']
        if any(not isclose(totals[e], tonggen['totals_after'][e], abs_tol=.000002)
               for e in '木火土金水'):
            return {**stopped, 'reason': '通根余额与五行汇总不一致。'}
        before = {e: round(totals[e], 6) for e in '木火土金水'}
        events, skipped = [], []
        qi_factor = {'本气': 1.0, '中气': .6, '余气': .4}
        abnormal = {'本气': .2, '中气': .1, '余气': .05}
        strong_root = {'本气': 1.0, '中气': 1.5, '余气': 2.0}
        strong_plain = {'本气': 1.5, '中气': 2.0, '余气': 2.5}
        medium_root = {'本气': .5, '中气': .8, '余气': 1.0}
        medium_plain = {'本气': .8, '中气': 1.2, '余气': 1.5}
        weak_root = {'本气': .1, '中气': .05, '余气': .02}
        weak_plain = {'本气': .2, '中气': .1, '余气': .05}
        for index in (2, 1, 3, 0):
            pillar = pillars[index]
            pid, actor = pillar['id'], pillar['stem']
            actor_element = LunarUtil.WU_XING_GAN[actor]
            branch_rows = [row for row in hidden_rows if row['pillar'] == pid]
            branch_rows.sort(key=lambda row: ELEMENT_ORDER.index(row['element']))
            for row in branch_rows:
                target, qi, target_element = row['stem'], row['qi'], row['element']
                active = audited[(pid, target)]['status']
                if active not in ('active_main', 'active_group_target'):
                    continue
                if CONTROLS[actor_element] != target_element:
                    if GENERATES[actor_element] == target_element:
                        return {**stopped, 'reason': '此受限路径尚未覆盖透干生藏干。'}
                    skipped.append({'pillar': pid, 'actor': actor, 'target': target,
                                    'reason': '本柱透干与此已激活藏干无生克关系。'})
                    continue
                actor_key, target_key = (pid, actor), (pid, target)
                actor_score, target_score = visible[actor_key], hidden[target_key]
                if min(actor_score, target_score, totals[target_element]) <= 0:
                    return {**stopped, 'reason': '受限生克来源余额或分母非正。'}
                global_ratio = totals[actor_element] / totals[target_element]
                current_ratio = actor_score / target_score
                if global_ratio <= .2 and current_ratio < abnormal[qi]:
                    return {**stopped, 'reason': '可能触发反克，异常等级未审核。'}
                if (global_ratio >= 1.5 and current_ratio >= strong_root[qi]) or (
                        global_ratio >= 2 and current_ratio >= strong_plain[qi]):
                    level = '强克'
                elif (global_ratio < 2.5 and current_ratio >= medium_root[qi]) or (
                        global_ratio < 2 and current_ratio >= medium_plain[qi]):
                    level = '中克'
                elif (global_ratio < 1.5 and current_ratio >= weak_root[qi]) or (
                        global_ratio < 1.2 and current_ratio >= weak_plain[qi]):
                    level = '弱克'
                else:
                    return {**stopped, 'reason': '未达到已审核的常规克等级。'}
                config = SHENGKE_RULES['normal_levels']['克'][level]
                polarity = .6 if ((actor in YANG) != (target in YANG) and
                                    global_ratio > .8 and current_ratio > .8) else 1.0
                delta = min(actor_score, target_score) * config['coefficient'] * qi_factor[qi] * polarity * SHENGKE_RULES['common_adjustment']
                actor_change = delta * config['actor_delta_ratio'] * SHENGKE_RULES['actor_loss']
                target_change = delta * config['target_delta_ratio']
                visible[actor_key] += actor_change
                hidden[target_key] += target_change
                if any(not isfinite(score) or score < 0 for score in (visible[actor_key], hidden[target_key])):
                    return {**stopped, 'reason': '生克后逐干余额无效。'}
                totals[actor_element] += actor_change
                totals[target_element] += target_change
                events.append({'pillar': pid, 'branch': pillar['branch'], 'actor': actor,
                               'target': target, 'qi': qi, 'relation': '克', 'level': level,
                               'ratio_global': round(global_ratio, 6),
                               'ratio_current': round(current_ratio, 6),
                               'polarity_coefficient': polarity,
                               'base_delta': round(delta, 6),
                               'actor_before': round(actor_score, 6),
                               'actor_change': round(actor_change, 6),
                               'actor_after': round(visible[actor_key], 6),
                               'target_before': round(target_score, 6),
                               'target_change': round(target_change, 6),
                               'target_after': round(hidden[target_key], 6)})
        return {'version': 'bazi-group-first-pass-2', 'status': 'isolated_first_pass',
                'reason': '按旧柱序和五行槽序复算唯一非本气克及其余常规克。',
                'events': events, 'skipped': skipped,
                'visible_balances_after': [dict(row, score=visible[(row['pillar'], row['stem'])])
                                           for row in visible_rows],
                'hidden_balances_after': [dict(row, score=hidden[(row['pillar'], row['stem'])])
                                          for row in hidden_rows],
                'totals_before': before,
                'totals_after': {e: round(totals[e], 6) for e in '木火土金水'}}
    except (KeyError, ValueError, TypeError):
        return {**stopped, 'reason': '会合生克输入缺失或无效。'}
