"""Restricted audit and replay of the legacy environment suppression stage.

The fixed pre-stage totals decide every gate. Effects themselves use the current
item balances in the old loop order. This is a score-stage trace, not a verdict.
"""
import json
from collections import Counter
from math import isclose, isfinite, log
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import PILLARS
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_environment_v1.json').read_text())
FIVE = '木火土金水'
ORDER = tuple(RULES['wuxing_names'])
VERSION = 'bazi-environment-audit-1'
REPLAY_VERSION = 'bazi-environment-replay-1'


def _stop(reason, replay=False):
    result = {'version': REPLAY_VERSION if replay else VERSION,
              'status': 'not_covered', 'reason': reason,
              'scope': '仅已覆盖生克后的环境压制技术规则；不计算旺衰或最终取用。',
              'dominant_element': None, 'same_force': None,
              'direct': [], 'indirect': [], 'totals_before': None, 'totals_after': None}
    if replay:
        result.update({'events': [], 'visible_balances_after': None,
                       'hidden_balances_after': None})
    return result


def _inputs(pillars, visible_pass):
    if visible_pass.get('status') != 'isolated_visible_pass':
        raise ValueError('透干间生克阶段未完整复算')
    if len(pillars) != 4 or [row.get('id') for row in pillars] != list(PILLARS):
        raise ValueError('四柱顺序不完整')
    visible = visible_pass.get('visible_balances_after')
    hidden = visible_pass.get('hidden_balances_after')
    given = visible_pass.get('totals_after')
    if not isinstance(visible, list) or not isinstance(hidden, list) or not isinstance(given, dict):
        raise ValueError('生克后逐干余额或汇总缺失')
    expected_hidden = {(p['id'], stem) for p in pillars
                       for stem in WEIGHT_RULES['branch_qi_type'][p['branch']]}
    if (len(visible) != 4 or len(hidden) != len(expected_hidden) or
            [r['pillar'] for r in visible] != list(PILLARS) or
            {(r['pillar'], r['stem']) for r in hidden} != expected_hidden or
            len({(r['pillar'], r['stem']) for r in hidden}) != len(hidden) or
            set(given) != set(FIVE)):
        raise ValueError('生克后逐干项目与四柱不一致')
    totals = Counter()
    for row in visible + hidden:
        pillar = pillars[PILLARS.index(row['pillar'])]
        score = row['score']
        if (row['stem'] not in LunarUtil.WU_XING_GAN or
                row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                not isinstance(score, (int, float)) or not isfinite(score) or score < 0):
            raise ValueError('生克后逐干属性或余额无效')
        if row in visible:
            if row['stem'] != pillar['stem']:
                raise ValueError('透干与四柱不一致')
        elif (row['branch'] != pillar['branch'] or
              row['qi'] != WEIGHT_RULES['branch_qi_type'][pillar['branch']][row['stem']]):
            raise ValueError('藏干与四柱不一致')
        totals[row['element']] += score
    if any(not isinstance(given[e], (int, float)) or not isfinite(given[e]) or
           not isclose(given[e], totals[e], rel_tol=0, abs_tol=.000002) for e in FIVE):
        raise ValueError('生克后逐干余额与汇总不一致')
    return visible, hidden, {e: totals[e] for e in FIVE}


def audit(pillars, visible_pass):
    try:
        visible, hidden, totals = _inputs(pillars, visible_pass)
        month_ratio = RULES['month_wuxing_ratio'][pillars[1]['branch']]
        if set(month_ratio) != set(FIVE) or sum(totals.values()) <= 0:
            raise ValueError('月令五行比值或总分缺失')
        if set(ORDER) != set(FIVE) or len(ORDER) != 5:
            raise ValueError('旧环境五行遍历顺序不完整')
        dominant = max(ORDER, key=lambda e: totals[e])
        dominant_score = totals[dominant]
        same_force = [dominant, RULES['wuxing_shengke'][dominant]['被生']]
        direct = []
        for target in ORDER:
            if target in same_force:
                continue
            score = totals[target]
            if score <= .001:
                direct.append({'target': target, 'status': 'tiny_score_skipped',
                               'target_score': round(score, 6), 'ratio': None,
                               'main_share': None, 'month_bonus': month_ratio[target],
                               'coefficient': None})
                continue
            ratio = dominant_score / score
            share = dominant_score / sum(totals.values())
            level, base = (('绝压', .5) if ratio >= 20 and share > .7 else
                           ('重压', .8) if ratio >= 10 and share > .6 else
                           ('中压', .9) if ratio >= 5 and share > .5 else (None, None))
            coefficient = None
            if base is not None:
                coefficient = (base + (.1 if month_ratio[target] > 1.5 else 0)) / (1 + .05 * log(ratio))
            direct.append({'target': target, 'status': level or 'no_effect',
                           'target_score': round(score, 6), 'ratio': round(ratio, 6),
                           'main_share': round(share, 6), 'month_bonus': month_ratio[target],
                           'coefficient': coefficient})
        indirect = []
        for target in ORDER:
            score = totals[target]
            if score <= .001:
                indirect.append({'target': target, 'status': 'tiny_score_skipped',
                                 'support': None, 'support_enemy': None,
                                 'support_score': None, 'enemy_score': None,
                                 'damage_ratio': None})
                continue
            support = RULES['wuxing_shengke'][target]['被生']
            enemy = RULES['wuxing_shengke'][support]['被克']
            support_score, enemy_score = totals[support], totals[enemy]
            if support_score < .001:
                # The old loop continues here before its isolation branch.
                status, damage = 'support_tiny_skipped', None
            elif enemy_score > 1.5 * support_score:
                status = 'indirect_effect'
                damage = min(.2, enemy_score / (support_score * 2) * .2)
            else:
                status, damage = 'enemy_below_threshold', None
            indirect.append({'target': target, 'status': status,
                             'support': support, 'support_enemy': enemy,
                             'support_score': round(support_score, 6),
                             'enemy_score': round(enemy_score, 6),
                             'damage_ratio': damage})
        return {'version': VERSION, 'status': 'audited',
                'reason': '按生克后原始总分固定直接与间接压制门槛；逐项作用另行复算。',
                'scope': '仅已覆盖生克后的环境压制技术规则；不计算旺衰或最终取用。',
                'dominant_element': dominant, 'same_force': same_force,
                'direct': direct, 'indirect': indirect,
                'totals_before': {e: round(totals[e], 6) for e in FIVE},
                'totals_after': None}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return _stop(str(exc))


def replay(pillars, visible_pass, audit_result):
    canonical = audit(pillars, visible_pass)
    if canonical['status'] != 'audited' or audit_result != canonical:
        return _stop('环境压制门槛未完整核对', replay=True)
    try:
        source_visible, source_hidden, _ = _inputs(pillars, visible_pass)
        visible = [dict(row) for row in source_visible]
        hidden = [dict(row) for row in source_hidden]
        rows = visible + hidden
        events = []

        def change(element, kind, factor=None, amount=None, position=False, target=None):
            reduction = 0.0
            for row in rows:
                if row['element'] != element or row['score'] <= 0:
                    continue
                before = row['score']
                if factor is not None:
                    after = max(0, before * factor)
                    if position and row in visible:
                        after *= (1.2 if row['pillar'] == 'month' else
                                  1.0 if row['pillar'] == 'day' else .8)
                else:
                    after = max(0, before - amount)
                row['score'] = after
                reduction += before - after
                events.append({'kind': kind, 'target': target or element,
                               'position': 'visible' if row in visible else 'hidden',
                               'pillar': row['pillar'], 'stem': row['stem'],
                               'element': element, 'before': round(before, 6),
                               'after': round(after, 6), 'delta': round(after-before, 6)})
            return reduction

        for rule in audit_result['direct']:
            if rule['coefficient'] is not None:
                change(rule['target'], 'direct', factor=rule['coefficient'],
                       position=True)
        for rule in audit_result['indirect']:
            if rule['status'] != 'indirect_effect':
                continue
            reduction = change(rule['support'], 'indirect_source',
                               factor=1-rule['damage_ratio'], target=rule['target'])
            if reduction > 0:
                change(rule['target'], 'indirect_sync', amount=reduction*.3)
        totals = Counter()
        for row in rows:
            if not isfinite(row['score']) or row['score'] < 0:
                raise ValueError('环境作用后逐干余额无效')
            totals[row['element']] += row['score']
        return {'version': REPLAY_VERSION, 'status': 'isolated_environment_stage',
                'reason': '直接与间接作用按旧顺序复算；所有门槛仍取作用前五行总分。',
                'scope': '仅已覆盖生克后的环境压制技术规则；不计算旺衰或最终取用。',
                'dominant_element': audit_result['dominant_element'],
                'same_force': audit_result['same_force'],
                'direct': audit_result['direct'], 'indirect': audit_result['indirect'],
                'events': events, 'visible_balances_after': visible,
                'hidden_balances_after': hidden,
                'totals_before': audit_result['totals_before'],
                'totals_after': {e: round(totals[e], 6) for e in FIVE}}
    except (KeyError, TypeError, ValueError) as exc:
        return _stop(str(exc), replay=True)
