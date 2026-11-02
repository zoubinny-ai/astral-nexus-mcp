"""Ordered active-hidden-qi-to-visible replay from the audited legacy table."""
from collections import Counter
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES, YANG
from astral_nexus_mcp.engines.bazi_shengke_reverse_probe import ORDER, PILLARS
from astral_nexus_mcp.engines.bazi_shengke_reverse_rules import calculate as calculate_reverse
from astral_nexus_mcp.engines.bazi_hidden_activation import active_hidden
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-shengke-reverse-pass-3'
ELEMENT_ORDER = '金木水火土'


def _stop(reason, stopped_at=None):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '第一段之后已激活藏干→本柱透干顺序复算；透干优先级分配未执行。',
            'stopped_at': stopped_at, 'events': [], 'skipped': [],
            'visible_balances_after': None, 'hidden_balances_after': None,
            'totals_before': None, 'totals_after': None}


def replay(pillars: list[dict], first_pass: dict, branch_replay: dict | None = None):
    if first_pass.get('status') != 'isolated_first_pass':
        return _stop('前序生克第一段未完整复算。')
    if len(pillars) != 4 or [p.get('id') for p in pillars] != list(PILLARS):
        return _stop('四柱顺序不完整。')
    visible_rows = first_pass.get('visible_balances_after')
    hidden_rows = first_pass.get('hidden_balances_after')
    source_totals = first_pass.get('totals_after')
    if not isinstance(visible_rows, list) or not isinstance(hidden_rows, list) or not isinstance(source_totals, dict):
        return _stop('前序逐干余额或五行汇总缺失。')
    try:
        expected_visible = {(p['id'], p['stem']) for p in pillars}
        expected_hidden = {(p['id'], stem) for p in pillars
                           for stem in WEIGHT_RULES['branch_qi_type'][p['branch']]}
        visible = {(r['pillar'], r['stem']): r['score'] for r in visible_rows}
        hidden = {(r['pillar'], r['stem']): r['score'] for r in hidden_rows}
        if (len(visible_rows) != 4 or len(hidden_rows) != len(expected_hidden) or
                set(visible) != expected_visible or set(hidden) != expected_hidden or
                set(source_totals) != set('木火土金水')):
            return _stop('前序逐干项目与四柱不一致。')
        totals = Counter()
        for row, is_hidden in ([(row, False) for row in visible_rows] +
                               [(row, True) for row in hidden_rows]):
            pillar = pillars[PILLARS.index(row['pillar'])]
            score = row['score']
            if (row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                    not isinstance(score, (int, float)) or not isfinite(score) or score < 0 or
                    (is_hidden and (row.get('branch') != pillar['branch'] or
                     row.get('qi') != WEIGHT_RULES['branch_qi_type'][pillar['branch']][row['stem']]))):
                return _stop('前序逐干属性或余额无效。')
            totals[row['element']] += score
        if any(not isinstance(source_totals[e], (int, float)) or not isfinite(source_totals[e]) or
               not isclose(totals[e], source_totals[e], abs_tol=.000002) for e in '木火土金水'):
            return _stop('前序逐干余额与五行汇总不一致。')
    except (KeyError, TypeError, ValueError):
        return _stop('前序逐干项目缺失或无法核对。')
    before = {e: round(totals[e], 6) for e in '木火土金水'}
    events, skipped = [], []
    try:
        active = active_hidden(pillars, branch_replay)
    except (KeyError, TypeError, ValueError):
        return _stop('前序会合激活项目无法核对。')
    for index in ORDER:
        pillar = pillars[index]
        pillar_id, target = pillar['id'], pillar['stem']
        hidden_slots = sorted(WEIGHT_RULES['branch_qi_type'][pillar['branch']].items(),
                              key=lambda item: ELEMENT_ORDER.index(LunarUtil.WU_XING_GAN[item[0]]))
        for actor, qi in hidden_slots:
            if (pillar_id, actor) not in active:
                continue
            outcome = _apply_slot(pillar, actor, target, qi, visible, hidden, totals,
                                  hidden_rows, events, skipped)
            if outcome:
                return _stop(outcome, pillar_id)
    return {'version': VERSION, 'status': 'isolated_reverse_pass',
            'reason': '按日、月、时、年与旧五行槽序复算已激活藏干对本柱透干生克。',
            'scope': '第二段已激活藏干作用；透干优先级分配尚未计算。',
            'stopped_at': None, 'events': events, 'skipped': skipped,
            'visible_balances_after': [dict(row, score=visible[(row['pillar'], row['stem'])])
                                       for row in visible_rows],
            'hidden_balances_after': [dict(row, score=hidden[(row['pillar'], row['stem'])])
                                      for row in hidden_rows],
            'totals_before': before,
            'totals_after': {e: round(totals[e], 6) for e in '木火土金水'}}


def _apply_slot(pillar, actor, target, qi, visible, hidden, totals,
                hidden_rows, events, skipped):
    pillar_id = pillar['id']
    actor_element = LunarUtil.WU_XING_GAN[actor]
    target_element = LunarUtil.WU_XING_GAN[target]
    relation = ('生' if GENERATES[actor_element] == target_element else
                '克' if CONTROLS[actor_element] == target_element else None)
    if relation is None:
        skipped.append({'pillar': pillar_id, 'hidden_stem': actor, 'visible_stem': target,
                        'reason': '已激活藏干对透干无生克关系。'})
        return None
    actor_key, target_key = (pillar_id, actor), (pillar_id, target)
    actor_score, target_score = hidden[actor_key], visible[target_key]
    if min(actor_score, target_score, totals[target_element]) <= 0:
        return '反向关系的来源余额或分母非正，不能用零值补齐。'
    global_ratio = totals[actor_element] / totals[target_element]
    current_ratio = actor_score / target_score
    same_polarity = (actor in YANG) == (target in YANG)
    # The legacy caller repeats the visible polarity. Use the configured
    # actor/target polarity here and record this explicit audit correction.
    target_has_root = any(row['element'] == target_element and
                          hidden[(row['pillar'], row['stem'])] > 0 for row in hidden_rows)
    operation = calculate_reverse(actor_score, target_score, global_ratio,
                                  current_ratio, relation, actor, target,
                                  target_has_root, qi)
    level, delta = operation['level'], operation['delta']
    polarity = operation['polarity_coefficient']
    hidden_change, visible_change = operation['hidden_change'], operation['visible_change']
    if delta == 0:
        skipped.append({'pillar': pillar_id, 'hidden_stem': actor,
                        'visible_stem': target, 'reason': '旧配置判定' + level + '，无变化。'})
        return None
    hidden[actor_key] += hidden_change
    visible[target_key] += visible_change
    totals[actor_element] += hidden_change
    totals[target_element] += visible_change
    events.append({'pillar': pillar_id, 'branch': pillar['branch'],
                   'hidden_stem': actor, 'visible_stem': target,
                   'relation': relation, 'level': level, 'qi': qi,
                   'same_polarity': same_polarity,
                   'polarity_coefficient': polarity,
                   'ratio_global': round(global_ratio, 6), 'ratio_current': round(current_ratio, 6),
                   'visible_has_root': target_has_root, 'base_delta': round(delta, 6),
                   'hidden_before': round(actor_score, 6), 'hidden_change': round(hidden_change, 6),
                   'hidden_after': round(hidden[actor_key], 6),
                   'visible_before': round(target_score, 6), 'visible_change': round(visible_change, 6),
                   'visible_after': round(visible[target_key], 6)})
    return None
