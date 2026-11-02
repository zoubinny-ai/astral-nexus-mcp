"""Versioned sui-yun relationship facts, with effects kept explicitly unresolved.

Sources: fortune_analysis/dayun_analyzer.py (internal stem/hidden stem,
dayun-to-natal stems and staged branch relations),
fortune_analysis/liunian_analyze.py (overlap of annual and luck periods), and
engines/data/bazi_interactions_v1.json (reviewed natal relation names).
Legacy auspice points, occupation side effects and numeric deltas are not
inferred from a structural match.
"""

from datetime import datetime
from itertools import combinations
from math import isfinite

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_interactions import RULES as BRANCH_RULES, STAGES
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES
from astral_nexus_mcp.engines.bazi_environment import RULES as ENV_RULES
from astral_nexus_mcp.engines.birth_time import CalculationError

VERSION = 'bazi-luck-interactions-3'
OLD_VERSION = 'bazi-luck-interactions-1'
PRIOR_VERSION = 'bazi-luck-interactions-2'
GENERATES = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
CONTROLS = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
HE = {frozenset('甲己'): '土', frozenset('乙庚'): '金',
      frozenset('丙辛'): '水', frozenset('丁壬'): '木',
      frozenset('戊癸'): '火'}
PILLARS = ('year', 'month', 'day', 'hour')
QI_WEIGHT_KEYS = {'本气': 'main_qi', '中气': 'middle_qi', '余气': 'remaining_qi'}
OLD_ORDER = ('five_he', 'sanhui', 'sanhe', 'liuhe', 'chong', 'sanxing',
             'xing', 'hai', 'po', 'banhe', 'gonghe')
OLD_PRIORITY = {'sanhui': 1, 'sanhe': 2, 'liuhe': 3, 'chong': 3,
                'sanxing': 4, 'banhe': 4, 'xing': 4, 'gonghe': 4,
                'hai': 5, 'po': 6, 'five_he': 7}
OLD_STRENGTH_GATE = {'liuhe': 30, 'banhe': 20}


def _node(name, gan_zhi):
    if (not isinstance(gan_zhi, str) or len(gan_zhi) != 2 or
            gan_zhi[0] not in LunarUtil.WU_XING_GAN or
            gan_zhi[1] not in LunarUtil.ZHI_HIDE_GAN or
            LunarUtil.getJiaZiIndex(gan_zhi) < 0):
        raise CalculationError('INVALID_LUCK_REPORT', '岁运干支不在六十甲子中')
    return {'id': name, 'stem': gan_zhi[0], 'branch': gan_zhi[1]}


def _relationship(first, second):
    a, b = LunarUtil.WU_XING_GAN[first], LunarUtil.WU_XING_GAN[second]
    if a == b:
        return 'same', None
    if GENERATES[a] == b:
        return 'generates', 'first_to_second'
    if GENERATES[b] == a:
        return 'generates', 'second_to_first'
    if CONTROLS[a] == b:
        return 'controls', 'first_to_second'
    if CONTROLS[b] == a:
        return 'controls', 'second_to_first'
    raise ValueError('incomplete five element relationship')


def _internal(node):
    """The source lists each hidden stem separately; no branch total is invented."""
    rows = []
    for stem in LunarUtil.ZHI_HIDE_GAN[node['branch']]:
        kind, direction = _relationship(node['stem'], stem)
        rows.append({'stem': stem,
                     'qi': WEIGHT_RULES['branch_qi_type'][node['branch']][stem],
                     'relation': kind, 'direction': direction,
                     'status': 'structural_only'})
    return {'pillar': node['id'], 'stem': node['stem'], 'branch': node['branch'],
            'stem_hidden_relations': rows, 'effect_status': 'not_covered'}


def _old_dayun_baseline(node):
    """Legacy pre-interaction weights only; never a post-interaction effect."""
    branch = node['branch']
    weights = WEIGHT_RULES['branch_qi_weight'][branch]
    hidden = {stem: weights[QI_WEIGHT_KEYS[qi]] * 2
              for stem, qi in WEIGHT_RULES['branch_qi_type'][branch].items()}
    return {'status': 'baseline_only', 'visible_stem': 20.0,
            'hidden_stems': hidden,
            'source': 'fortune_analysis/dayun_analyzer.py::get_dayun_scores',
            'limitation': '旧大运固定作用前权重；不是占用、成化或生克后的余额，也不是流年权重。'}


def _old_stem_conditions(node, natal, visible):
    """Replay the legacy diagnostic formula, without inventing score transfers.

    The legacy implementation compares a pillar name to a stem character when
    attempting to skip the current target. That comparison never succeeds. We
    retain the observed arithmetic here and flag it rather than silently
    treating its priority as a post-interaction score.
    """
    if (visible.get('status') != 'isolated_environment_stage' or
            not isinstance(visible.get('visible_balances_after'), list)):
        return {'status': 'not_covered', 'reason': '原盘环境阶段逐干余额未完整复算。'}
    scores = visible['visible_balances_after']
    if (len(scores) != 4 or
            any(row.get('pillar') != pillar['id'] or row.get('stem') != pillar['stem'] or
                type(row.get('score')) not in (int, float) or
                not isfinite(row['score']) or row['score'] < 0
                for row, pillar in zip(scores, natal))):
        raise ValueError('natal visible balances mismatch')
    dayun_element = LunarUtil.WU_XING_GAN[node['stem']]
    controlled = sum(row['score'] / 20 for row in scores
                     if CONTROLS[LunarUtil.WU_XING_GAN[row['stem']]] == dayun_element)
    drained = sum(row['score'] / 20 for row in scores
                  if GENERATES[dayun_element] == LunarUtil.WU_XING_GAN[row['stem']])
    strength = controlled + drained
    restraint = 'full' if strength >= 1.5 else 'partial' if strength >= .8 else 'none'
    restraint_multiplier = .1 if restraint == 'full' else .5 if restraint == 'partial' else 1.
    rows = []
    for target, score in zip(natal, scores):
        target_element = LunarUtil.WU_XING_GAN[target['stem']]
        intermediary = next((other for other in natal
                             if GENERATES[dayun_element] == LunarUtil.WU_XING_GAN[other['stem']]
                             and GENERATES[LunarUtil.WU_XING_GAN[other['stem']]] == target_element), None)
        ratio = 20 / score['score'] if score['score'] > 0 else None
        strength_multiplier = (1. if ratio is None or ratio >= 1.5 else
                               .8 if ratio >= 1 else .6)
        priority = restraint_multiplier * (1.5 if intermediary else 1.) * strength_multiplier
        rows.append({'target': target['id'], 'target_stem': target['stem'],
                     'natal_stage_score': score['score'],
                     'initial_dayun_stem_score': 20.,
                     'strength_ratio': ratio,
                     'zero_target_score_legacy_infinite_ratio': ratio is None,
                     'legacy_control_strength': controlled,
                     'legacy_drain_strength': drained,
                     'legacy_restraint_strength': strength,
                     'legacy_restraint': restraint,
                     'legacy_tongguan_via': intermediary['id'] if intermediary else None,
                     'legacy_priority': priority,
                     'effect_status': 'not_covered'})
    return {'status': 'legacy_diagnostic_only', 'relations': rows,
            'source': 'fortune_analysis/dayun_analyzer.py::check_zhihua_status / check_tongguan_effect / calculate_relationship_priority',
            'limitation': '旧制化函数按柱名与干名比较，实际未排除当前目标；这里保留旧算式供审核。优先级不是力量变化量，旧代码没有逐干作用后余额公式。'}


def _events(nodes, introduced):
    stems = []
    branches = []
    for first, second in combinations(nodes, 2):
        if introduced not in (first['id'], second['id']):
            continue
        pair = frozenset((first['stem'], second['stem']))
        if pair in HE:
            stems.append({'kind': 'five_he', 'participants': [first['id'], second['id']],
                          'stems': [first['stem'], second['stem']],
                          'possible_element': HE[pair], 'status': 'candidate_only'})
        kind, direction = _relationship(first['stem'], second['stem'])
        stems.append({'kind': kind, 'participants': [first['id'], second['id']],
                      'stems': [first['stem'], second['stem']],
                      'direction': direction, 'status': 'structural_only'})
    for _, kind, _ in STAGES:
        for key, info in BRANCH_RULES[kind].items():
            for group in combinations(nodes, len(key)):
                if introduced not in (node['id'] for node in group):
                    continue
                if sorted(node['branch'] for node in group) == sorted(key):
                    branches.append({'kind': kind, 'rule_key': key,
                                     'participants': [node['id'] for node in group],
                                     'branches': [node['branch'] for node in group],
                                     'possible_element': info['possible_element'],
                                     'status': 'candidate_only'})
    return {'stem_relations': stems, 'branch_relations': branches,
            'effect_status': 'not_covered',
            'reason': '结构关系已核对；岁运占用、成化、逐干变化量与吉凶尚未复算。'}


def _natal_occupied(evidence):
    """Only settled natal events can block a new luck relation."""
    branch = evidence['branch_replay']
    if branch['status'] != 'isolated_pair_stages':
        return None
    occupied = {}
    for event in branch['events']:
        if event.get('changes'):
            priority = OLD_PRIORITY.get(event['kind'])
            if priority is not None:
                for pillar in event['pillars']:
                    occupied[pillar] = min(occupied.get(pillar, 99), priority)
    return occupied


def _old_dayun_event_review(events, natal, node, evidence):
    """Apply old executable gates; never call a passed gate an energy delta."""
    totals = evidence['environment_replay'].get('totals_after')
    occupied = _natal_occupied(evidence)
    month_ratio = ENV_RULES['month_wuxing_ratio'][natal[1]['branch']]
    natal_he = {pillar for pair in evidence['five_he_audit'].get('applied_pairs', [])
                for pillar in pair}
    reviewed = []
    for event in events['stem_relations']:
        row = dict(event)
        if row['kind'] == 'five_he':
            element = row['possible_element']
            checks = {'target_score_gt_60': totals[element] > 60 if totals else None,
                      'month_ratio_at_least_0_8': month_ratio[element] >= .8,
                      'natal_stem_unoccupied': next(
                          p for p in row['participants'] if p != 'dayun') not in natal_he,
                      'legacy_interference_clear': not any(
                          CONTROLS[LunarUtil.WU_XING_GAN[p['stem']]] == element
                          for p in natal if p['id'] != 'month')}
            row['judgment'] = _judgment(checks)
            row['judgment']['source'] = 'dayun_analyzer.py::analyze_tiangan_he/check_hehua_success'
        reviewed.append(row)
    branch_rows = sorted(events['branch_relations'],
                         key=lambda row: (OLD_ORDER.index(row['kind']), row['participants']))
    formed_dayun = []
    for event in branch_rows:
        row = dict(event)
        kind = row['kind']
        participants = [p for p in row['participants'] if p != 'dayun']
        element = row['possible_element']
        checks = {'natal_occupation_known': True if occupied is not None else None}
        if occupied is not None:
            checks['no_higher_priority_natal_occupation'] = all(
                occupied.get(p, 99) >= OLD_PRIORITY[kind] for p in participants)
            if kind in ('sanhui', 'sanhe', 'liuhe', 'banhe', 'gonghe'):
                checks['no_natal_occupation'] = all(p not in occupied for p in participants)
        if kind in ('sanhui', 'sanhe', 'liuhe', 'banhe'):
            checks['month_ratio_at_least_0_8'] = month_ratio[element] >= .8
            if kind in OLD_STRENGTH_GATE:
                checks['target_score_at_least_threshold'] = (
                    totals[element] >= OLD_STRENGTH_GATE[kind] if totals else None)
            elif totals is None:
                checks['legacy_score_gate_available'] = None
            # The old sanhui/sanhe false branch still sets score_condition=True.
            row['legacy_low_score_gate_ignored'] = (
                totals[element] < 30 if kind in ('sanhui', 'sanhe') and totals else False)
        if kind == 'sanxing':
            checks.pop('no_higher_priority_natal_occupation', None)
        if formed_dayun and kind != 'sanxing':
            # Legacy branch-name occupation conflates duplicate natal positions.
            # A competing luck event is not promoted to a definite success.
            if any(set(row['participants']) & set(other) for other in formed_dayun):
                checks['no_competing_luck_relation'] = None
        row['judgment'] = _judgment(checks)
        row['judgment']['source'] = f'dayun_analyzer.py::analyze_{kind}'
        if row['judgment']['status'] == 'legacy_formed':
            formed_dayun.append(row['participants'])
        reviewed.append(row)
    return {**events, 'stem_relations': reviewed[:len(events['stem_relations'])],
            'branch_relations': reviewed[len(events['stem_relations']):],
            'effect_status': 'not_covered',
            'reason': '旧事件条件已审核；成立仅指旧关系谓词通过，不是力量变化或岁运吉凶。'}


def _judgment(checks):
    if any(value is False for value in checks.values()):
        status = 'blocked'
    elif any(value is None for value in checks.values()):
        status = 'undetermined'
    else:
        status = 'legacy_formed'
    return {'status': status, 'checks': checks,
            'limitation': '旧关系谓词；不表示逐干分数转移或年度吉凶。'}


def _unreviewed_annual(events):
    """The old annual analyzer has no event-success predicates."""
    def tag(row):
        if row['status'] == 'structural_only':
            return row
        return {**row, 'judgment': {'status': 'undetermined', 'checks': {},
                                     'source': 'liunian_analyze.py',
                                     'limitation': '旧流年仅按时间引用大运分析，没有此关系的成立判定。'}}
    return {**events, 'stem_relations': [tag(r) for r in events['stem_relations']],
            'branch_relations': [tag(r) for r in events['branch_relations']]}


def _path_definitions(evidence):
    result = []
    for scenario in evidence['pattern_review']['scenarios']:
        selected = scenario['useful_stem'].get('selected') or {}
        seasonal = scenario['conditional_evidence'].get('rules') or []
        matched = [row['name'] for row in scenario['auspicious_combinations']['patterns']
                   if row['status'] == 'matched']
        result.append({'id': scenario['id'], 'pattern': scenario['pattern'],
                       'assumptions': scenario['assumptions'], 'decision': 'conditional_only',
                       'useful_stem': selected.get('stem'),
                       'useful_status': scenario['useful_stem']['status'],
                       'seasonal_need_elements': sorted({rule['needed_element'] for rule in seasonal}),
                       'natal_matched_jixiong': matched,
                       'natal_jixiong_status': scenario['auspicious_combinations']['status'],
                       'uncovered_items': scenario['uncovered_items']})
    return result


def _path_lenses(node, paths):
    result = []
    for path in paths:
        target = path['useful_stem']
        kind, direction = _relationship(node['stem'], target) if target else (None, None)
        result.append({'path_id': path['id'], 'source_stem': node['stem'],
                       'conditional_useful_stem': target, 'relation': kind,
                       'direction': direction, 'status': 'conditional_structure' if target else 'not_covered',
                       'limitation': '只比较本柱透干与该路径条件用神的五行方向；不是岁运吉凶。'})
    return result


def _segments(annual, periods):
    start = datetime.fromisoformat(annual['start'])
    end = datetime.fromisoformat(annual['end_exclusive'])
    cuts = {start, end}
    for row in periods:
        for field in ('start', 'end_exclusive'):
            boundary = datetime.fromisoformat(row[field])
            if start < boundary < end:
                cuts.add(boundary)
    ordered = sorted(cuts)
    for left, right in zip(ordered, ordered[1:]):
        active = [row for row in periods
                  if datetime.fromisoformat(row['start']) <= left <
                  datetime.fromisoformat(row['end_exclusive'])]
        if len(active) > 1:
            raise CalculationError('INVALID_LUCK_REPORT', '大运区间重叠，无法分配流年')
        yield left, right, active[0] if active else None


def review(chart, fortune, *, version=VERSION):
    """Calculate exact temporal partitions and cross-layer relation facts."""
    try:
        rows = chart['pillars']
        if len(rows) != 4 or tuple(row['id'] for row in rows) != PILLARS:
            raise ValueError('natal pillar order')
        natal = []
        for row in rows:
            if row['gan_zhi'] != row['stem'] + row['branch']:
                raise ValueError('natal pillar contents')
            natal.append(_node(row['id'], row['gan_zhi']))
        if version not in (OLD_VERSION, PRIOR_VERSION, VERSION):
            raise ValueError('unknown interaction review version')
        evidence = None
        if version != OLD_VERSION:
            from astral_nexus_mcp.engines.bazi_evidence import extract
            evidence = extract(chart)
        paths = _path_definitions(evidence) if version == VERSION else None
        period_rows = []
        for period in fortune['periods']:
            node = _node('dayun', period['gan_zhi'])
            row = {'number': period['number'], 'gan_zhi': period['gan_zhi'],
                   'internal': _internal(node),
                   'old_initial_weights': _old_dayun_baseline(node),
                   'to_natal': _events([*natal, node], 'dayun')}
            if version != OLD_VERSION:
                row['old_stem_conditions'] = _old_stem_conditions(
                    node, natal, evidence['environment_replay'])
            if version == VERSION:
                row['to_natal'] = _old_dayun_event_review(row['to_natal'], natal, node, evidence)
                row['conditional_paths'] = _path_lenses(node, paths)
            period_rows.append(row)
        annual_rows = []
        for annual in fortune['annual']:
            annual_node = _node('liunian', annual['gan_zhi'])
            intervals = []
            for left, right, period in _segments(annual, fortune['periods']):
                nodes = [*natal]
                if period is not None:
                    nodes.append(_node('dayun', period['gan_zhi']))
                nodes.append(annual_node)
                segment = {'start': left.isoformat(), 'end_exclusive': right.isoformat(),
                           'period_number': period['number'] if period else None,
                           'liunian_internal': _internal(annual_node),
                           'liunian_to_natal_and_dayun': _events(nodes, 'liunian')}
                if version == VERSION:
                    segment['liunian_to_natal_and_dayun'] = _unreviewed_annual(
                        segment['liunian_to_natal_and_dayun'])
                    segment['conditional_paths'] = _path_lenses(annual_node, paths)
                intervals.append(segment)
            if {row['period_number'] for row in intervals if row['period_number']} != set(annual['overlapping_periods']):
                raise ValueError('annual period overlap mismatch')
            annual_rows.append({'year': annual['year'], 'gan_zhi': annual['gan_zhi'],
                                'segments': intervals})
        result = {'version': version, 'status': 'structural_review',
                'periods': period_rows, 'annual': annual_rows,
                'limits': ['干支内部、岁运与原盘的结构关系可追溯；命中不等于生效。',
                           '占用、成化、作用前后分数、各条件格局的岁运吉凶尚未覆盖。'] if version == OLD_VERSION else
                          ['干支内部、岁运与原盘的结构关系可追溯；命中不等于生效。',
                           '旧大运初始权重与天干制化／通关／优先级可审；优先级不是实际作用后的分数。',
                           '旧流年无独立初始力量赋分；流年仍只列分段结构关系。',
                           '占用、成化、逐干实际变化量与各条件格局的岁运吉凶尚未覆盖。']}
        if version == VERSION:
            result['conditional_paths'] = paths
            result['limits'] = [
                '大运关系的成立／受阻仅按已列旧谓词审核；多事件竞争与不足的占用来源保留未判定，不代表力量增减。',
                '流年按实际区间与大运／原盘列结构；旧程序无流年关系成立判定或独立初始分数。',
                '每条格局路径仅比较岁运透干与条件用神的五行方向；原局吉凶及调候不自动变为年度吉凶。',
                '首条格局为默认路径，后续路径可由用户切换；完整喜用五行未覆盖，年度吉凶分和作用后余额不输出。']
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise CalculationError('INVALID_LUCK_REPORT', '岁运作用输入与原盘或时间轴不一致') from exc
