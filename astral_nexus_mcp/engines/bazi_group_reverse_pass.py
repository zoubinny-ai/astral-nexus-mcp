"""Restricted reverse sheng-ke replay for one activated middle-qi event."""

from collections import Counter
from copy import deepcopy
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_group_activation import first_pass as replay_group_first
from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES, YANG
from astral_nexus_mcp.engines.bazi_shengke_reverse_pass import replay as replay_main
from astral_nexus_mcp.engines.bazi_shengke_reverse_probe import ORDER, PILLARS, RULES

VERSION = 'bazi-group-reverse-pass-2'


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'events': [], 'visible_balances_after': None, 'hidden_balances_after': None,
            'totals_before': None, 'totals_after': None}


def _non_main_level(qi, relation, global_ratio, current_ratio, target_has_root):
    """Legacy non-main reverse thresholds, in configuration order."""
    factor = {'中气': 1.0, '余气': 4 / 3}[qi]
    if relation == '生':
        if global_ratio >= 3 and current_ratio >= (4 if qi == '中气' else 5):
            return '异常'
        if ((target_has_root and global_ratio >= 1 and current_ratio >= 1.8 * factor) or
                (global_ratio >= 1.5 and current_ratio >= 2.7 * factor)):
            return '强生'
        if ((target_has_root and global_ratio >= .8 and current_ratio >= 1.2 * factor) or
                (global_ratio >= 1.2 and current_ratio >= 1.8 * factor)):
            return '中生'
        if ((global_ratio > .3 and current_ratio >= .45 * factor) or
                (target_has_root and global_ratio > .1 and current_ratio > .1)):
            return '弱生'
    else:
        if global_ratio <= .2 and current_ratio < (.1 if qi == '中气' else .05):
            return '异常'
        if global_ratio >= 2 and current_ratio >= (2 if qi == '中气' else 2.5):
            return '强克'
        if global_ratio < 2 and current_ratio >= (1.2 if qi == '中气' else 1.5):
            return '中克'
        if global_ratio < 1.2 and current_ratio >= (.1 if qi == '中气' else .05):
            return '弱克'
    return None


def replay(pillars, activation, tonggen, first_pass):
    if first_pass != replay_group_first(pillars, activation, tonggen):
        return _stop('会合盘第一段余额与审核输入不一致。')
    if first_pass['status'] != 'isolated_first_pass':
        return _stop('会合盘第一段未完整复算。')
    main = replay_main(pillars, first_pass)
    if main['status'] != 'isolated_reverse_pass':
        return _stop('本气反向段未完整复算：' + main['reason'])
    activated = activation['activated_non_main']
    relations, inactive = [], []
    for item in activated:
        if item['qi'] not in ('中气', '余气'):
            return _stop('非本气激活气类无法核对。')
        target_element = LunarUtil.WU_XING_GAN[pillars[PILLARS.index(item['pillar'])]['stem']]
        if GENERATES[item['element']] == target_element or CONTROLS[item['element']] == target_element:
            relations.append(item)
        else:
            inactive.append({'pillar': item['pillar'], 'hidden_stem': item['stem'],
                             'visible_stem': pillars[PILLARS.index(item['pillar'])]['stem'],
                             'qi': item['qi'], 'reason': '激活藏干对本柱透干无生克关系。'})
    if not relations:
        return {'version': VERSION, 'status': 'isolated_group_reverse_pass',
                'reason': '本气反向段已复算；激活非本气均无反向生克关系。',
                'events': main['events'], 'skipped': main['skipped'] + inactive,
                'visible_balances_after': main['visible_balances_after'],
                'hidden_balances_after': main['hidden_balances_after'],
                'totals_before': first_pass['totals_after'],
                'totals_after': main['totals_after']}
    if len(relations) != 1:
        return _stop('实际非本气反向生克不是唯一关系；多项顺序作用尚未复算。')
    row = relations[0]
    index = PILLARS.index(row['pillar'])
    if any(ORDER.index(PILLARS.index(event['pillar'])) >= ORDER.index(index)
           for event in main['events']):
        return _stop('已激活中气之前或同柱存在被延后执行的本气作用。')
    pillar = pillars[index]
    actor, target = row['stem'], pillar['stem']
    actor_element = row['element']
    target_element = LunarUtil.WU_XING_GAN[target]
    relation = ('生' if GENERATES[actor_element] == target_element else
                '克' if CONTROLS[actor_element] == target_element else None)
    if relation is None:
        return _stop('非本气关系无法核对。')
    result = deepcopy(main)
    result['skipped'].extend(inactive)
    hidden = next(item for item in result['hidden_balances_after']
                  if item['pillar'] == row['pillar'] and item['stem'] == actor)
    visible = next(item for item in result['visible_balances_after']
                   if item['pillar'] == row['pillar'])
    actor_score, target_score = hidden['score'], visible['score']
    totals = Counter()
    for item in result['visible_balances_after'] + result['hidden_balances_after']:
        totals[item['element']] += item['score']
    if any(not isclose(totals[e], result['totals_after'][e], abs_tol=.000002)
           for e in '木火土金水'):
        return _stop('本气反向逐干余额与汇总不一致。')
    if min(actor_score, target_score, totals[target_element]) <= 0:
        return _stop('中气来源余额或目标分母非正。')
    global_ratio = totals[actor_element] / totals[target_element]
    current_ratio = actor_score / target_score
    target_has_root = any(item['element'] == target_element and item['score'] > 0
                          for item in result['hidden_balances_after'])
    # The acting hidden stem is a positive root of its own element. The legacy
    # normal-level dispatcher tests either side for a root.
    level = _non_main_level(row['qi'], relation, global_ratio, current_ratio,
                            target_has_root or actor_score > 0)
    if level == '异常':
        return _stop('非本气候选触发旧异常生克，数值规则尚未审核。')
    if level is None:
        result['skipped'].append({'pillar': row['pillar'], 'hidden_stem': actor,
                                  'visible_stem': target, 'qi': row['qi'],
                                  'reason': '实际反向关系未达到旧配置常规作用门槛，旧配置返回无变化。'})
        return {'version': VERSION, 'status': 'isolated_group_reverse_pass',
                'reason': '本气反向段已复算；唯一非本气关系按旧配置门槛判定为无变化。',
                'events': result['events'], 'skipped': result['skipped'],
                'visible_balances_after': result['visible_balances_after'],
                'hidden_balances_after': result['hidden_balances_after'],
                'totals_before': first_pass['totals_after'],
                'totals_after': result['totals_after']}
    same_polarity = (actor in YANG) == (target in YANG)
    polarity = RULES[('different_yin_yang_' if not same_polarity and
                      global_ratio > .8 and current_ratio > .8 else
                      'same_yin_yang_') + ('generate' if relation == '生' else 'control')]
    config = RULES['normal_levels'][relation][level]
    delta = min(actor_score, target_score) * config['coefficient'] * {
        '中气': .6, '余气': .4}[row['qi']] * polarity * RULES['common_adjustment']
    hidden_change = delta * config['hidden_delta_ratio']
    visible_change = delta * config['visible_delta_ratio'] * RULES['visible_loss']
    hidden['score'] += hidden_change
    visible['score'] += visible_change
    if not all(isfinite(value) and value >= 0 for value in (hidden['score'], visible['score'])):
        return _stop('非本气作用后余额无效。')
    sums = Counter()
    for item in result['visible_balances_after'] + result['hidden_balances_after']:
        sums[item['element']] += item['score']
    after = {element: round(sums[element], 6) for element in '木火土金水'}
    if any(not isclose(after[e], totals[e] + (hidden_change if e == actor_element else 0) +
                       (visible_change if e == target_element else 0), abs_tol=.000003)
           for e in '木火土金水'):
        return _stop('非本气作用后逐干汇总不一致。')
    result['events'].append({'pillar': row['pillar'], 'branch': row['branch'],
                             'hidden_stem': actor, 'visible_stem': target, 'qi': row['qi'],
                             'relation': relation, 'level': level,
                             'ratio_global': round(global_ratio, 6),
                             'ratio_current': round(current_ratio, 6),
                             'polarity_coefficient': polarity,
                             'base_delta': round(delta, 6),
                             'hidden_before': round(actor_score, 6),
                             'hidden_change': round(hidden_change, 6),
                             'hidden_after': round(hidden['score'], 6),
                             'visible_before': round(target_score, 6),
                             'visible_change': round(visible_change, 6),
                             'visible_after': round(visible['score'], 6)})
    return {'version': VERSION, 'status': 'isolated_group_reverse_pass',
            'reason': '本气顺序段与唯一实际非本气反向关系均完成受限复算；无关系激活项已跳过。',
            'events': result['events'], 'skipped': result['skipped'],
            'visible_balances_after': result['visible_balances_after'],
            'hidden_balances_after': result['hidden_balances_after'],
            'totals_before': first_pass['totals_after'], 'totals_after': after}
