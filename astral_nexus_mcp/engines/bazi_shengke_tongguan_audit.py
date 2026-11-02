"""Restricted structural review of legacy visible-stem mediation paths."""
from math import isclose, isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_shengke_probe import CONTROLS, GENERATES

VERSION = 'bazi-shengke-tongguan-audit-1'
PILLARS = ('year', 'month', 'day', 'hour')
PATHS = ((0, 1, 2), (0, 2, 3), (1, 2, 3), (2, 1, 0), (3, 2, 1), (3, 1, 0))


def _stop(reason):
    return {'version': VERSION, 'status': 'not_covered', 'reason': reason,
            'scope': '只核对透干间通关路径与旧状态；制化、合化、综合优先级和分配未执行。',
            'paths': [], 'priority_order': None, 'allocations': None, 'totals_after': None}


def audit(pillars: list[dict], reverse_pass: dict, priority_inputs: dict):
    if (reverse_pass.get('status') not in ('isolated_reverse_pass', 'isolated_group_reverse_pass') or
            priority_inputs.get('status') != 'inputs_only'):
        return _stop('前序反向本气或透干关系输入未完整覆盖。')
    if len(pillars) != 4 or [p.get('id') for p in pillars] != list(PILLARS):
        return _stop('四柱顺序不完整。')
    rows = reverse_pass.get('visible_balances_after')
    relationships = priority_inputs.get('relationships')
    if not isinstance(rows, list) or not isinstance(relationships, list):
        return _stop('前序透干余额或关系列表缺失。')
    try:
        visible = {(row['pillar'], row['stem']): row for row in rows}
        if len(rows) != 4 or set(visible) != {(p['id'], p['stem']) for p in pillars}:
            return _stop('透干余额与四柱不一致。')
        for row in rows:
            score = row['score']
            if (row['element'] != LunarUtil.WU_XING_GAN[row['stem']] or
                    not isinstance(score, (int, float)) or not isfinite(score) or score <= 0):
                return _stop('透干属性或余额无效。')
        expected = {}
        for actor in pillars:
            actor_element = LunarUtil.WU_XING_GAN[actor['stem']]
            for target in pillars:
                if actor['id'] == target['id']:
                    continue
                target_element = LunarUtil.WU_XING_GAN[target['stem']]
                relation = ('生' if GENERATES[actor_element] == target_element else
                            '克' if CONTROLS[actor_element] == target_element else None)
                if relation:
                    expected[(actor['id'], target['id'])] = relation
        if (len(relationships) != len(expected) or
                {(rel['actor_pillar'], rel['target_pillar']): rel['relation']
                 for rel in relationships} != expected):
            return _stop('透干关系列表与四柱不一致。')
        for rel in relationships:
            actor = pillars[PILLARS.index(rel['actor_pillar'])]
            target = pillars[PILLARS.index(rel['target_pillar'])]
            actor_score = visible[(actor['id'], actor['stem'])]['score']
            target_score = visible[(target['id'], target['stem'])]['score']
            if (rel['actor_stem'] != actor['stem'] or rel['target_stem'] != target['stem'] or
                    not isclose(rel['actor_before'], actor_score, abs_tol=.000002) or
                    not isclose(rel['target_before'], target_score, abs_tol=.000002)):
                return _stop('关系双方与反向阶段余额不一致。')
    except (KeyError, TypeError, ValueError):
        return _stop('前序透干关系无法核对。')
    paths = []
    for rel in relationships:
        actor_index = PILLARS.index(rel['actor_pillar'])
        target_index = PILLARS.index(rel['target_pillar'])
        actor = pillars[actor_index]
        target = pillars[target_index]
        actor_element = LunarUtil.WU_XING_GAN[actor['stem']]
        target_element = LunarUtil.WU_XING_GAN[target['stem']]
        actor_score = visible[(actor['id'], actor['stem'])]['score']
        matches = []
        for middle_index, middle in enumerate(pillars):
            if middle_index in (actor_index, target_index):
                continue
            triple = tuple(sorted((actor_index, middle_index, target_index)))
            allowed = any(tuple(sorted(path)) == triple and
                          (actor_index < middle_index < target_index or
                           actor_index > middle_index > target_index) for path in PATHS)
            if not allowed:
                continue
            middle_element = LunarUtil.WU_XING_GAN[middle['stem']]
            middle_score = visible[(middle['id'], middle['stem'])]['score']
            if (GENERATES[actor_element] == middle_element and
                    GENERATES[middle_element] == target_element and middle_score > 0):
                matches.append({'middle_pillar': middle['id'], 'middle_stem': middle['stem'],
                                'middle_before': round(middle_score, 6),
                                'actor_before': round(actor_score, 6),
                                'status': 'partial' if actor_score > middle_score * 2 else 'full'})
                break  # Legacy takes the first qualifying middle stem.
        paths.append({'actor_pillar': actor['id'], 'actor_stem': actor['stem'],
                      'target_pillar': target['id'], 'target_stem': target['stem'],
                      'relation': rel['relation'], 'path': matches[0] if matches else None})
    return {'version': VERSION, 'status': 'structural_review',
            'reason': '已核对允许的透干通关路径及作用前强弱条件；其他状态与分配未复算。',
            'scope': '只核对透干间通关路径与旧状态；制化、合化、综合优先级和分配未执行。',
            'paths': paths, 'priority_order': None, 'allocations': None, 'totals_after': None}
