"""Ordered visible-to-active-hidden-qi replay from the audited legacy table."""
from collections import Counter

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES, probe
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES
from astral_nexus_mcp.engines.bazi_shengke_first_rules import calculate as calculate_first
from astral_nexus_mcp.engines.bazi_hidden_activation import active_hidden

VERSION = 'bazi-shengke-first-pass-4'
ORDER = (2, 1, 3, 0)  # Executable legacy order: day, month, hour, year.
ELEMENT_ORDER = '金木水火土'


def _stop(reason, stopped_at=None):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '本柱透干对已激活藏干的顺序复算；反向藏干与透干分配尚未执行。',
            'stopped_at': stopped_at, 'events': [], 'skipped': [],
            'visible_balances_after': None, 'hidden_balances_after': None,
            'totals_before': None, 'totals_after': None}


def replay(pillars: list[dict], tonggen: dict, branch_replay: dict | None = None):
    """Replay all active hidden slots in the legacy pillar and element order."""
    first = probe(pillars, tonggen)
    if tonggen.get('status') != 'isolated_tonggen_stage':
        return _stop('前序通根阶段未完整复算。')
    if first['status'] != 'isolated_first_operation' and first['reason'] in (
            '前序逐干属性或余额无效。', '前序逐干余额与五行汇总不一致。',
            '前序逐干项目缺失或无法核对。', '前序逐干项目与四柱不一致。',
            '四柱顺序不完整。'):
        return _stop('生克输入无法核对：' + first['reason'])
    visible_rows = tonggen['visible_balances_after']
    hidden_rows = tonggen['hidden_balances_after']
    visible = {(row['pillar'], row['stem']): row['score'] for row in visible_rows}
    hidden = {(row['pillar'], row['stem']): row['score'] for row in hidden_rows}
    totals = Counter()
    for row in visible_rows + hidden_rows:
        totals[row['element']] += row['score']
    before = {element: round(totals[element], 6) for element in '木火土金水'}
    events, skipped = [], []
    try:
        active = active_hidden(pillars, branch_replay)
    except (KeyError, TypeError, ValueError):
        return _stop('前序会合激活项目无法核对。')
    for index in ORDER:
        pillar = pillars[index]
        pillar_id, actor = pillar['id'], pillar['stem']
        hidden_slots = sorted(WEIGHT_RULES['branch_qi_type'][pillar['branch']].items(),
                              key=lambda item: ELEMENT_ORDER.index(LunarUtil.WU_XING_GAN[item[0]]))
        for target, qi in hidden_slots:
            if (pillar_id, target) not in active:
                continue
            actor_element = LunarUtil.WU_XING_GAN[actor]
            target_element = LunarUtil.WU_XING_GAN[target]
            relation = ('生' if GENERATES[actor_element] == target_element else
                        '克' if CONTROLS[actor_element] == target_element else None)
            if relation is None:
                skipped.append({'pillar': pillar_id, 'actor': actor, 'target': target,
                                'reason': '本柱透干与已激活藏干无生克关系。'})
                continue
            actor_key, target_key = (pillar_id, actor), (pillar_id, target)
            actor_score, target_score = visible[actor_key], hidden[target_key]
            if min(actor_score, target_score, totals[target_element]) <= 0:
                return _stop('此步来源余额或分母非正，不能用零值补齐。', pillar_id)
            global_ratio = totals[actor_element] / totals[target_element]
            current_ratio = actor_score / target_score
            actor_has_root = any(row['element'] == actor_element and hidden[(row['pillar'], row['stem'])] > 0
                                 for row in hidden_rows)
            target_has_root = any(row['element'] == target_element and
                                  hidden[(row['pillar'], row['stem'])] > 0 for row in hidden_rows)
            operation = calculate_first(actor_score, target_score, global_ratio,
                                        current_ratio, relation, actor, target,
                                        actor_has_root, target_has_root, qi)
            level, delta = operation['level'], operation['delta']
            polarity = operation['polarity_coefficient']
            actor_change, target_change = operation['actor_change'], operation['target_change']
            if delta == 0:
                skipped.append({'pillar': pillar_id, 'actor': actor, 'target': target,
                                'reason': '旧配置判定' + level + '，无变化。'})
                continue
            visible[actor_key] += actor_change
            hidden[target_key] += target_change
            totals[actor_element] += actor_change
            totals[target_element] += target_change
            events.append({'pillar': pillar_id, 'actor': actor, 'target': target, 'branch': pillar['branch'],
                           'relation': relation, 'level': level, 'qi': qi,
                           'ratio_global': round(global_ratio, 6), 'ratio_current': round(current_ratio, 6),
                           'actor_has_root': actor_has_root, 'polarity_coefficient': polarity,
                           'base_delta': round(delta, 6),
                           'actor_before': round(actor_score, 6), 'actor_change': round(actor_change, 6),
                           'actor_after': round(visible[actor_key], 6),
                           'target_before': round(target_score, 6), 'target_change': round(target_change, 6),
                           'target_after': round(hidden[target_key], 6)})
    return {'version': VERSION, 'status': 'isolated_first_pass',
            'reason': '按日、月、时、年与旧五行槽序复算本柱透干对已激活藏干生克。',
            'scope': '第一段已激活藏干作用；未执行反向藏干作用和透干优先级分配。',
            'stopped_at': None, 'events': events, 'skipped': skipped,
            'visible_balances_after': [
                {'pillar': row['pillar'], 'stem': row['stem'], 'element': row['element'],
                 'score': visible[(row['pillar'], row['stem'])]} for row in visible_rows],
            'hidden_balances_after': [
                {'pillar': row['pillar'], 'branch': row['branch'], 'stem': row['stem'],
                 'element': row['element'], 'qi': row['qi'], 'score': hidden[(row['pillar'], row['stem'])]}
                for row in hidden_rows],
            'totals_before': before,
            'totals_after': {element: round(totals[element], 6) for element in '木火土金水'}}
