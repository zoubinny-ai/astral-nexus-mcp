"""Audit the legacy day-pillar void branches without implying a pattern verdict."""
import json
from pathlib import Path

from astral_nexus_mcp.engines.bazi_interactions import PILLAR_IDS

VERSION = 'bazi-kongwang-audit-1'
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_kongwang_v1.json').read_text())
STEMS = '甲乙丙丁戊己庚辛壬癸'
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'
PRIOR_KINDS = frozenset(('sanhui', 'sanhe', 'liuhe', 'chong', 'sanxing', 'banhe'))


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '仅审核日柱旬空和旧空亡函数的作用门槛；不等于地支阶段已复算。',
            'xun_shou': None, 'empty_branches': None, 'prior_candidates': [],
            'numeric_coverage': False, 'positions': [], 'totals_after': None}


def audit(pillars: list[dict], interaction_audit: dict):
    try:
        if len(pillars) != 4 or tuple(row['id'] for row in pillars) != PILLAR_IDS:
            raise ValueError('四柱顺序不完整')
        if any(row['stem'] not in STEMS or row['branch'] not in BRANCHES or
               row['gan_zhi'] != row['stem'] + row['branch'] for row in pillars):
            raise ValueError('四柱干支无法核对')
        day = pillars[2]
        stem_index, branch_index = STEMS.index(day['stem']), BRANCHES.index(day['branch'])
        if stem_index % 2 != branch_index % 2:
            raise ValueError('日柱干支阴阳不符，无法确定旬空')
        start = (branch_index - stem_index) % 12
        xun_shou = '甲' + BRANCHES[start]
        expected = [BRANCHES[(start + 10) % 12], BRANCHES[(start + 11) % 12]]
        empty = RULES['xun_kong'][xun_shou]
        if empty != expected:
            raise ValueError('旬空表与日柱推算不一致')
        events = interaction_audit['branch_events']
        if any(row['kind'] not in PRIOR_KINDS | {'xing', 'gonghe', 'hai', 'po'}
               for row in events):
            raise ValueError('地支候选阶段未知')
        prior = [{'kind': row['kind'], 'pillars': row['pillars'],
                  'branches': row['branches']} for row in events
                 if row['kind'] in PRIOR_KINDS and not
                 (row['kind'] in ('liuhe', 'banhe') and
                  row['condition_review'].get('grade_if_reached') == 'none_if_reached')]
        occurrences = []
        for row in pillars:
            is_empty = row['branch'] in empty
            occurrences.append({'pillar': row['id'], 'branch': row['branch'],
                                'is_empty': is_empty,
                                'legacy_reduction_ratio': .3 if is_empty and not prior else None,
                                'reason': ('前序会合或六冲候选尚未确定占用' if is_empty and prior else
                                           '旬空且在受限盘中无前序占用' if is_empty else
                                           '非旬空地支')})
        numeric_coverage = not prior or not any(row['is_empty'] for row in occurrences)
        return {'version': VERSION, 'status': 'audited',
                'reason': ('存在旬空与前序候选重叠，须由地支阶段确认实际作用与占用。' if not numeric_coverage else
                           '已核对旬首、旬空柱位及受限盘前序占用边界。'),
                'scope': '仅审核日柱旬空和旧空亡函数的作用门槛；不等于地支阶段已复算。',
                'xun_shou': xun_shou, 'empty_branches': empty,
                'prior_candidates': prior, 'numeric_coverage': numeric_coverage,
                'positions': occurrences, 'totals_after': None}
    except (KeyError, TypeError, ValueError) as exc:
        return _stop(str(exc))
