"""Conditional useful-stem and auspicious-combination evidence for each pattern path.

Rules are snapshotted from the old configuration. Unknown predicates stay unknown.
"""

import json
from pathlib import Path

from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.bazi_jixiong_predicates import JixiongContext

VERSION = 'bazi-path-outcomes-3'
PATTERNS = json.loads((Path(__file__).parent / 'data' / 'bazi_jixiong_v1.json').read_text())
CLASSES = {
    '比劫': ('比肩', '劫财'), '印星': ('正印', '偏印'),
    '官杀': ('正官', '七杀'), '食伤': ('食神', '伤官'),
    '财星': ('正财', '偏财'),
}
COUNTER = {'比劫': '官杀', '官杀': '食伤', '印星': '财星',
           '食伤': '印星', '财星': '比劫'}
PILLARS = ('year', 'month', 'day', 'hour')


def _group(god):
    return next((key for key, values in CLASSES.items() if god in values), None)


def select_useful_stem(pillars, reverse_pass, roles):
    """Old mingju.py compares allocation.total_score, set before visible interactions."""
    if reverse_pass.get('status') != 'isolated_reverse_pass' or not roles:
        return {'status': 'not_covered', 'reason': '透干分配前逐干余额或本路径格神配置缺失。',
                'selected': None, 'candidates': []}
    visible = reverse_pass.get('visible_balances_after') or []
    if len(visible) != 4 or [row.get('pillar') for row in visible] != list(PILLARS):
        return {'status': 'not_covered', 'reason': '最终透干账本柱序缺失。',
                'selected': None, 'candidates': []}
    eligible = set(roles['格神'] + roles['相神'])
    candidates = []
    for pillar, balance in zip(pillars, visible):
        if pillar['id'] == 'day':
            continue
        stem, score = pillar['stem'], balance.get('score')
        if balance.get('stem') != stem or not isinstance(score, (int, float)) or score < 0:
            return {'status': 'not_covered', 'reason': '最终透干与命盘或余额不一致。',
                    'selected': None, 'candidates': []}
        god = LunarUtil.SHI_SHEN[pillars[2]['stem'] + stem]
        group = _group(god)
        candidates.append({'pillar': pillar['id'], 'stem': stem, 'ten_god': god,
                           'class': group, 'score': round(score, 6),
                           'eligible': group in eligible})
    ranked = [row for row in candidates if row['eligible'] and row['score'] > 0]
    selected = max(ranked, key=lambda row: row['score']) if ranked else None
    if selected is None:
        return {'status': 'no_visible_candidate', 'selected': None,
                'candidates': candidates,
                'role_fallback': list(roles['格神']),
                'reason': '旧程序退回格神类别，但没有实际透干可选；不伪造实际用神。'}
    demoted = COUNTER[selected['class']]
    remaining = list(dict.fromkeys(roles['格神'] + roles['相神']))
    if demoted in remaining:
        remaining.remove(demoted)
    return {'status': 'conditional_selected', 'selected': selected,
            'candidates': candidates, 'demoted_counter_class': demoted,
            'supporting_classes': [row for row in remaining if row != selected['class']],
            'source': 'shengke_processor.py: allocation.total_score before visible interactions; geju_analysis/mingju.py: repeated selection',
            'reason': '在所选格局路径下，该透干按旧分配前最大正余额规则入选；切换路径需重新取用。'}


def combinations(pattern, pillars, strength, environment=None,
                 first_pass=None, reverse_pass=None, visible_pass=None):
    """Every old configured condition is reported; unresolved conditions never match."""
    level = strength.get('stage_level')
    context = JixiongContext(pillars, environment or {}, first_pass or {},
                             reverse_pass or {}, visible_pass or {})
    rows = []
    for item in PATTERNS['patterns']:
        if pattern not in item['geju_type']:
            continue
        conditions = item['conditions']
        facts = []
        allowed = conditions.get('rizhu', [])
        matched = level in allowed if level is not None else None
        facts.append({'kind': 'rizhu', 'condition': '／'.join(allowed),
                      'status': 'matched' if matched else 'unmatched' if matched is False else 'not_covered',
                      'basis': f'八维旺衰：{level}' if level else '八维旺衰未完成。',
                      'required': True})
        for term in conditions.get('position', []):
            value, basis = context.predicate(term, kind='position')
            facts.append({'kind': 'position', 'condition': term,
                          'status': 'matched' if value else 'unmatched' if value is False else 'not_covered',
                          'basis': basis, 'required': True})
        for kind in ('chengge', 'poge'):
            block = conditions.get(kind, {})
            for grade, terms in block.items():
                for term in terms:
                    value, basis = context.predicate(term, kind=kind + '.' + grade)
                    facts.append({'kind': f'{kind}.{grade}', 'condition': term,
                                  'status': 'matched' if value else 'unmatched' if value is False else 'not_covered',
                                  'basis': basis,
                                  'required': grade == 'required' and
                                  ((kind == 'chengge' and item['jixiong'] == '吉') or
                                   (kind == 'poge' and item['jixiong'] == '凶'))})
        for term in conditions.get('position_conditions', []):
            facts.append({'kind': 'position_conditions', 'condition': term,
                          'status': 'informational', 'required': False,
                          'basis': '旧配置的自然语言位置说明，不作为布尔条件。'})
        required = [fact['status'] for fact in facts if fact['required']]
        avoid = [fact['status'] for fact in facts
                 if item['jixiong'] == '吉' and fact['kind'] == 'chengge.avoid']
        # core.py calls the checker with is_level_match=False: avoid is recorded
        # but cannot veto the initial pattern match. level_analyzer.py later
        # calls it with True and does apply the avoid gate.
        status = ('unmatched' if 'unmatched' in required else
                  'not_covered' if 'not_covered' in required else
                  'matched')
        rows.append({'name': item['name'], 'jixiong': item['jixiong'],
                     'status': status, 'conditions': facts,
                     'level_avoid_status': ('not_covered' if 'not_covered' in avoid else
                                            'blocked' if 'matched' in avoid else
                                            'clear') if avoid else None})
    return {'status': 'conditional_evaluated' if rows else 'no_configured_patterns',
            'source': PATTERNS['source'], 'patterns': rows,
            'uncovered_conditions': sorted({f['condition'] for row in rows
                                            for f in row['conditions'] if f['status'] == 'not_covered'})}
