"""Restricted twelve-life-stage replay after reviewed branch and five-he stages."""
import json
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

VERSION = 'bazi-life-stages-audit-1'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_life_stages_v1.json').read_text())
PILLAR_IDS = ('year', 'month', 'day', 'hour')
EVENT_LABELS = {'chong': '地支六冲', 'xing': '地支相刑',
                'hai': '地支相害', 'po': '地支相破',
                'sanhui': '地支三会', 'sanhe': '地支三合',
                'liuhe': '地支六合', 'banhe': '地支半合',
                'gonghe': '地支拱合', 'sanxing': '地支三刑'}


def _unavailable(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅在前序地支和五合阶段覆盖时，复算各透干坐支十二长生；不是最终五行力量。',
            'rows': [], 'totals_before': None, 'totals_after': None}


def replay(pillars: list[dict], branch_replay: dict, five_he: dict):
    """Apply the old reviewed coefficient to each visible stem, with event-level damping."""
    if branch_replay['status'] not in ('isolated_pair_stages', 'isolated_group_branch_stage'):
        return _unavailable('前序地支阶段未完整复算。')
    if five_he['status'] not in ('no_candidate', 'guard_failed', 'isolated_partial_stage',
                                  'isolated_complete_stage'):
        return _unavailable('五合阶段仍有未审核的分数转移。')
    source_totals = (five_he['totals_after'] if five_he['status'] in ('isolated_partial_stage',
                                                                      'isolated_complete_stage')
                     else branch_replay['totals_after'])
    if source_totals is None:
        return _unavailable('前序阶段缺少可核对的五行汇总。')
    totals = dict(source_totals)
    before = dict(totals)
    stem_scores = {p['id']: float(WEIGHT_RULES['stem_base_weight'][LunarUtil.WU_XING_GAN[p['stem']]])
                   for p in pillars}
    for change in five_he['changes']:
        stem_scores[change['from_pillar']] -= change['amount']
        stem_scores[change['to_pillar']] += change['amount']
    rows = []
    for pillar in pillars:
        pillar_id, stem, branch = pillar['id'], pillar['stem'], pillar['branch']
        stage = RULES[stem][branch]
        event_weight = 1.0
        events = []
        for index, event in enumerate(branch_replay['events']):
            if pillar_id not in event['pillars']:
                continue
            level = '完全' if event['grade'].startswith('完全') else '部分'
            label = EVENT_LABELS[event['kind']]
            configured = stage['event_weights'].get(level, {}).get(label, 1.0)
            if configured < 1:
                event_weight *= 1 - (1 - configured) * .5
            events.append({'event_index': index, 'label': label, 'level': level,
                           'configured_weight': configured})
        coefficient = max(.5, min(2.5, 1 + (stage['weight'] * event_weight - 1) * .5))
        stem_before = stem_scores[pillar_id]
        stem_after = round(stem_before * coefficient, 2)
        element = LunarUtil.WU_XING_GAN[stem]
        totals[element] = round(totals[element] + stem_after - stem_before, 6)
        rows.append({'pillar': pillar_id, 'stem': stem, 'branch': branch,
                     'element': element, 'state': stage['state'],
                     'base_weight': stage['weight'], 'event_weight': round(event_weight, 6),
                     'coefficient': round(coefficient, 6), 'before': round(stem_before, 6),
                     'after': stem_after, 'delta': round(stem_after - stem_before, 6),
                     'events': events})
    return {'version': VERSION, 'status': 'isolated_life_stages',
            'reason': '已按前序实际两支事件及五合结果，逐透干复算坐支十二长生。',
            'scope': '仅受限盘的十二长生阶段快照；月令、通根、生克及最终格局仍未计算。',
            'rows': rows, 'totals_before': before, 'totals_after': totals}
