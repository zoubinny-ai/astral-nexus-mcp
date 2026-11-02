"""Audited legacy decision dependencies and conditional seasonal lookup.

No layer here decides a pattern or useful element. Missing prerequisites remain explicit.
"""

import json
from pathlib import Path

from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES
from astral_nexus_mcp.engines.bazi_wangshuai_inputs import probe as probe_strength_inputs
from astral_nexus_mcp.engines.bazi_pattern_selection import evaluate as evaluate_selection
from astral_nexus_mcp.engines.bazi_path_outcomes import select_useful_stem, combinations

VERSION = 'bazi-pattern-review-13'
LOOKUP = json.loads((Path(__file__).parent / 'data' / 'bazi_tiaohou_v1.json').read_text())
TIAOHOU_CORRECTIONS = json.loads((Path(__file__).parent / 'data' / 'bazi_tiaohou_corrections_v1.json').read_text())
ROLES = json.loads((Path(__file__).parent / 'data' / 'bazi_pattern_roles_v1.json').read_text())
ORDINARY_ROLES = json.loads((Path(__file__).parent / 'data' / 'bazi_ordinary_pattern_roles_v1.json').read_text())
LAYERS = (
    ('transformation', '化气格', ('日干五合事件', '完整五行分数', '八项旺衰等级')),
    ('dominant', '专旺格', ('完整五行分数', '八项旺衰等级', '根气与刑冲合会')),
    ('follow_strong', '从旺格', ('完整五行分数', '八项旺衰等级', '根气与生扶克泄')),
    ('follow_weak', '从弱／从势格', ('完整五行分数', '八项旺衰等级', '根气与生扶克泄')),
    ('lu_ren', '禄刃格', ('前四层排除结果', '月令与根气')),
    ('month_pattern', '月令正格', ('前五层排除结果', '月令透藏权重', '十神分数')),
)
STRENGTH_INPUTS = ('完整五行分数', '逐干及印比克泄余额', '根气强弱', '月令比例',
                   '同柱得生', '八项评分边界')
QI_WEIGHT = {'本气': 3, '中气': 2, '余气': 1}
PRODUCER = {'木': '水', '火': '木', '土': '火', '金': '土', '水': '金'}
ZHENGGE = {'正官': '正官格', '七杀': '七杀格', '正印': '正印格',
           '偏印': '偏印格', '正财': '正财格', '偏财': '偏财格',
           '食神': '食神格', '伤官': '伤官格'}
GOD_CLASS = {'正印': '印星', '偏印': '印星', '比肩': '比劫', '劫财': '比劫',
             '正官': '官杀', '七杀': '官杀', '食神': '食伤', '伤官': '食伤',
             '正财': '财星', '偏财': '财星'}
SEASONAL_LEVELS = ('严重不足', '调候不足', '稍有不足', '调候适中', '调候过强')
SEASONAL_STATES = {
    '寒湿调候': ('寒湿', '偏寒湿', '稍寒湿', '适中', '偏暖燥'),
    '暖燥调候': ('暖燥', '偏暖燥', '稍暖燥', '适中', '偏寒湿'),
}
SEASONAL_POINTS = {'寒湿': 30, '偏寒湿': 60, '稍寒湿': 70,
                   '适中': 100, '稍暖燥': 70, '偏暖燥': 60, '暖燥': 30}


def _main_stem(pillar):
    return next(item['stem'] for item in pillar['hidden_stems']
                if WEIGHT_RULES['branch_qi_type'][pillar['branch']][item['stem']] == '本气')


def _seasonal_stage(rule, day_element, day_score, environment, identity=None):
    if environment.get('status') != 'isolated_environment_stage':
        return {'status': 'not_covered', 'reason': '环境阶段未完整复算。'}
    thresholds = rule['thresholds']
    original_names = list(thresholds)
    if rule['type'] not in SEASONAL_STATES or len(original_names) != 5:
        return {'status': 'not_covered', 'reason': '调候类型或五级阈值配置不完整。'}
    # All 738 old entries use the same five ordinal slots. 69 contain misspelled
    # labels; normalize only the slot label, while exposing every correction.
    corrections = [{'slot': index + 1, 'source_label': name,
                    'normalized_label': SEASONAL_LEVELS[index]}
                   for index, name in enumerate(original_names)
                   if name != SEASONAL_LEVELS[index]]
    if corrections and identity is not None:
        pattern, day, month = identity
        registered = [{key: row[key] for key in ('slot', 'source_label', 'normalized_label')}
                      for row in TIAOHOU_CORRECTIONS['corrections']
                      if (row['pattern'], row['day_stem'], row['month_branch'], row['type']) ==
                      (pattern, day, month, rule['type']) and
                      row['threshold'] == thresholds.get(row['source_label'])]
        if registered != corrections:
            return {'status': 'not_covered', 'reason': '调候错键未在逐条审核快照中注册。'}
    values = [thresholds[name] for name in original_names]
    if any(not isinstance(value, (int, float)) or value < 0 for value in values):
        return {'status': 'not_covered', 'reason': '调候阈值缺失或无效。'}
    element = rule['needed_element']
    totals = environment['totals_after']
    if element not in totals:
        return {'status': 'not_covered', 'reason': '所需五行阶段余额缺失。'}
    element_score = totals[element]
    class_score = element_score - day_score if element == day_element else element_score
    if class_score < -0.00001:
        return {'status': 'not_covered', 'reason': '所需十神类余额无法对账。'}
    intensity = (max(0.0, class_score) + element_score) / 2
    # Legacy _match_demand_level sorts by numeric threshold, retaining insertion
    # order on ties. Six old records are non-monotone or tied; sorting is material.
    ordered = sorted(enumerate(values), key=lambda row: row[1])
    index = next((position for position, threshold in ordered
                  if intensity < threshold), ordered[-1][0])
    state = SEASONAL_STATES[rule['type']][index]
    return {'status': 'conditional_corrected' if corrections else 'conditional_stage',
            'element_score': round(element_score, 6),
            'class_score': round(max(0.0, class_score), 6),
            'intensity': round(intensity, 6),
            'level': SEASONAL_LEVELS[index], 'climate_state': state,
            'conditional_score': SEASONAL_POINTS[state],
            'threshold_order': [SEASONAL_LEVELS[position] for position, _ in ordered],
            'label_corrections': corrections,
            'reason': ('旧键名按逐条审核快照的五级位置校正，原名与位置已列出；'
                       if corrections else '') +
                      '按所选格局路径适用；按旧阈值数值排序后匹配，余额为统一环境终值。'}


def _month_entry(pillars):
    month = pillars[1]
    branch = month['branch']
    candidates = []
    hidden = sorted(month['hidden_stems'],
                    key=lambda row: -QI_WEIGHT[WEIGHT_RULES['branch_qi_type'][branch][row['stem']]])
    for row in hidden:
        stem = row['stem']
        qi = WEIGHT_RULES['branch_qi_type'][branch][stem]
        element = LunarUtil.WU_XING_GAN[stem]
        visible = [p for p in pillars if p['id'] != 'day' and
                   p['stem_ten_god'] not in ('比肩', '劫财')]
        exact = next((p for p in visible if p['stem'] == stem and
                      p['stem_ten_god'] == row['ten_god']), None)
        same_element = next((p for p in visible if LunarUtil.WU_XING_GAN[p['stem']] == element), None)
        selected = exact or same_element
        if selected:
            candidates.append({'hidden_stem': stem, 'hidden_qi': qi,
                               'visible_pillar': selected['id'], 'visible_stem': selected['stem'],
                               'ten_god': selected['stem_ten_god'],
                               'match': 'same_stem_and_ten_god' if exact else 'same_element',
                               'structural_weight': QI_WEIGHT[qi] + (1.5 if exact else 1.0)})
    if not candidates:
        main = next(row for row in hidden if WEIGHT_RULES['branch_qi_type'][branch][row['stem']] == '本气')
        candidates.append({'hidden_stem': main['stem'], 'hidden_qi': '本气',
                           'visible_pillar': None, 'visible_stem': None,
                           'ten_god': main['ten_god'], 'match': 'main_qi_fallback',
                           'structural_weight': 3.0})
    positions = {row['hidden_qi'] for row in candidates}
    needs_final_scores = '本气' not in positions and {'中气', '余气'} <= positions
    return {'status': 'needs_final_scores' if needs_final_scores else 'structural_candidates',
            'candidates': candidates, 'requires_final_scores': needs_final_scores,
            'reason': ('中气与余气同时透出且本气未透，旧算法还要以最终五行分数补权重。'
                       if needs_final_scores else '只核对月令透藏结构与初始权重；前五层未排除，不可据此定正格。')}


def _follow_weak_stage(pillars, environment, stage_strength):
    """Replay legacy structural weights and ordered ratio gates on stage balances."""
    if stage_strength['stage_level'] != '极弱':
        return None
    day = pillars[2]['stem']
    element = LunarUtil.WU_XING_GAN[day]
    producer = PRODUCER[element]
    weights = {'no_root': 0.0, 'no_support_main_qi': 0.0,
               'no_peer_visible': 0.0, 'no_support_visible': 0.0}
    for index, pillar in enumerate(pillars):
        for hidden in pillar['hidden_stems']:
            hidden_element = LunarUtil.WU_XING_GAN[hidden['stem']]
            qi = WEIGHT_RULES['branch_qi_type'][pillar['branch']][hidden['stem']]
            if hidden_element == element:
                weights['no_root'] += (1, 2, 2, 1)[index] * {'本气': 2, '中气': 1.5, '余气': 1}[qi]
            if qi == '本气' and hidden_element == producer:
                factor = (0.8, 2, 2, 0.8)[index]
                if LunarUtil.WU_XING_GAN[pillar['stem']] == element or any(
                        LunarUtil.WU_XING_GAN[row['stem']] == producer for row in pillars):
                    factor *= 2
                weights['no_support_main_qi'] += factor
        visible_element = LunarUtil.WU_XING_GAN[pillar['stem']]
        if index != 2 and visible_element == element:
            weights['no_peer_visible'] += 1
        if visible_element == producer:
            weights['no_support_visible'] += 1
    total_violation = sum(weights.values())
    totals = environment['totals_after']
    total = sum(totals.values())
    day_share = stage_strength['inputs']['day_stem_score'] / total * 100
    classes = {name: 0.0 for name in ('印星', '比劫', '官杀', '食伤', '财星')}
    for stem, stem_element in LunarUtil.WU_XING_GAN.items():
        god = LunarUtil.SHI_SHEN[day + stem]
        if god in GOD_CLASS:
            classes[GOD_CLASS[god]] = totals[stem_element] / total * 100
    classes['比劫'] -= day_share
    yinbi = classes['印星'] + classes['比劫']
    gates = {
        '从财格': day_share < 10 and classes['财星'] > 60 and yinbi < 30,
        '从杀格': day_share < 10 and classes['官杀'] > 65 and yinbi < 30,
        '从儿格': day_share < 15 and classes['食伤'] > 60 and yinbi < 20,
        '从势格': day_share < 10 and
                  classes['财星'] + classes['官杀'] + classes['食伤'] > 75 and yinbi < 20,
    }
    selected = next((name for name, passed in gates.items() if passed), None) if total_violation <= 1.8 else None
    return {'status': 'stage_candidate' if selected else 'stage_gates_failed',
            'violation_weights': {key: round(value, 6) for key, value in weights.items()},
            'total_violation': round(total_violation, 6), 'structural_gate': total_violation <= 1.8,
            'day_stem_share': round(day_share, 6),
            'class_shares': {key: round(value, 6) for key, value in classes.items()},
            'yinbi_share': round(yinbi, 6), 'ordered_ratio_gates': gates,
            'pattern_if_confirmed': selected,
            'purity_if_final': (('真' if total_violation == 0 else '假') + selected) if selected else None,
            'limitation': '按旧结构权重、1.8门槛及从财→从杀→从儿→从势比例顺序复算完整环境余额；格局层次救应另审。'}


def _conditional_pattern(pattern, day, month, stage_strength, environment):
    rules = LOOKUP['rules'].get(pattern, {}).get(day, {}).get(month, [])
    roles = ROLES['rules'].get(pattern, {}).get(day)
    roles_branch = None
    if roles is None and pattern in ORDINARY_ROLES['rules'] and stage_strength['stage_level']:
        level = stage_strength['stage_level']
        roles_branch = ('强旺' if level == '极旺' else level
                        if level in ('中和', '偏旺', '强旺') else '其它')
        roles = ORDINARY_ROLES['rules'][pattern].get(roles_branch, {}).get(day)
    return {'pattern_if_confirmed': pattern, 'day_stem': day, 'month_branch': month,
            'status': 'conditional_lookup' if rules else 'config_missing',
            'reason': None if rules else f'旧调候配置缺少{pattern}／{day}日／{month}月规则。',
            'rules': [{**rule, 'stage_assessment': _seasonal_stage(
                rule, LunarUtil.WU_XING_GAN[day],
                stage_strength['inputs']['day_stem_score'], environment,
                (pattern, day, month))
                if stage_strength['inputs'] is not None else
                {'status': 'not_covered', 'reason': '旺衰输入前序未完成。'}} for rule in rules],
            'source': LOOKUP['source'], 'conditional_roles': roles,
            'roles_branch': roles_branch,
            'roles_source': ORDINARY_ROLES['source'] if roles_branch else ROLES['source'],
            'limitation': '仅当该格局经完整规则与经历确认时可使用；需求五行不是本盘已判定的调候用神。'}


def review(pillars: list[dict], *, five_he: dict, environment: dict,
           group_audit: dict | None = None, branch_replay: dict | None = None,
           reverse_pass: dict | None = None, first_pass: dict | None = None,
           visible_pass: dict | None = None) -> dict:
    """Expose exact prerequisites and only a pattern-conditional seasonal rule."""
    if len(pillars) != 4 or [p['id'] for p in pillars] != ['year', 'month', 'day', 'hour']:
        raise ValueError('四柱顺序无效')
    day = pillars[2]['stem']
    month = pillars[1]['branch']
    if day not in LunarUtil.WU_XING_GAN or month not in LunarUtil.ZHI_HIDE_GAN:
        raise ValueError('日干或月支无效')
    for row in (five_he, environment):
        if not isinstance(row, dict) or 'status' not in row:
            raise ValueError('前序阶段状态缺失')
    stage_strength = probe_strength_inputs(pillars, environment)

    transformation_probe = None
    follow_weak_probe = None
    day_candidates = [candidate for candidate in five_he.get('candidates', [])
                      if 'day' in candidate['pillars']]
    if (stage_strength['stage_level'] is not None and len(day_candidates) == 1 and
            five_he['status'] in ('isolated_partial_stage', 'isolated_complete_stage')):
        candidate = day_candidates[0]
        target = candidate['target_element']
        total = sum(environment['totals_after'].values())
        target_share = environment['totals_after'][target] / total * 100
        producer_share = environment['totals_after'][PRODUCER[target]] / total * 100
        gates = {'stage_extremely_weak': stage_strength['stage_level'] == '极弱',
                 'day_stem_is_non_target': LunarUtil.WU_XING_GAN[day] != target,
                 'target_at_least_50_percent': target_share >= 50,
                 'target_and_producer_at_least_80_percent': target_share + producer_share >= 80}
        transformation_probe = {
            'status': 'stage_candidate' if all(gates.values()) else 'stage_gates_failed',
            'pattern_if_confirmed': f'化{target}格',
            'purity_if_final': ('假化气格' if five_he['status'] == 'isolated_partial_stage'
                                else '真化气格'),
            'five_he_status': five_he['status'],
            'target_share': round(target_share, 6),
            'producer_share': round(producer_share, 6),
            'gates': gates,
            'limitation': '只按旧化气入口阈值和受限环境阶段试算；其余前序分支未完整覆盖，须由问答结合经历判断，不能作为最终格局。',
        }
    if stage_strength['stage_level'] == '极弱':
        day_element = LunarUtil.WU_XING_GAN[day]
        producer = PRODUCER[day_element]
        other_visible = [pillar for pillar in pillars if pillar['id'] != 'day']
        gates = {
            'no_day_element_hidden': not any(
                LunarUtil.WU_XING_GAN[item['stem']] == day_element
                for pillar in pillars for item in pillar['hidden_stems']),
            'no_producer_main_qi': not any(
                LunarUtil.WU_XING_GAN[_main_stem(pillar)] == producer
                for pillar in pillars),
            'no_same_element_visible_peer': not any(
                LunarUtil.WU_XING_GAN[pillar['stem']] == day_element for pillar in other_visible),
            'no_producer_visible': not any(
                LunarUtil.WU_XING_GAN[pillar['stem']] == producer for pillar in other_visible),
        }
        follow_weak_probe = {
            'status': 'structural_inputs_only', 'gates': gates,
            'unmet_count': sum(not passed for passed in gates.values()),
            'limitation': '只核对旧从格入口四项结构条件；后续从财、从杀、从儿、从势的比例与破格顺序未计算。',
        }

    stage_checks = {}
    if stage_strength['stage_level'] is not None:
        totals = environment['totals_after']
        all_score = sum(totals.values())
        day_element = LunarUtil.WU_XING_GAN[day]
        month_element = LunarUtil.WU_XING_GAN[_main_stem(pillars[1])]
        day_share = totals[day_element] / all_score * 100
        day_stem_share = stage_strength['inputs']['day_stem_score'] / all_score * 100
        support_share = (totals[day_element] + totals[PRODUCER[day_element]]) / all_score * 100
        stage_checks = {
            'transformation': transformation_probe['gates'] if transformation_probe else None,
            'dominant': {
                'stage_extremely_strong': stage_strength['stage_level'] == '极旺',
                'month_matches_day_element': month_element == day_element,
                'day_element_at_least_80_percent': day_share >= 80,
                'matching_group_structure': (any(
                    row['target_element'] == day_element
                    for row in group_audit.get('candidates', [])) if group_audit else None),
            },
            'follow_strong': {
                'stage_extremely_strong': stage_strength['stage_level'] == '极旺',
                'month_matches_day_element': month_element == day_element,
                'day_stem_over_20': day_stem_share > 20,
                'support_over_80_percent': support_share > 80,
                'opposition_under_20_percent': 100 - support_share < 20,
            },
            'follow_weak': ({'stage_extremely_weak': True,
                             **follow_weak_probe['gates']} if follow_weak_probe else
                            {'stage_extremely_weak': False}),
            'lu_ren': {
                'month_main_peer_or_rob_wealth': LunarUtil.SHI_SHEN[day + _main_stem(pillars[1])]
                in ('比肩', '劫财'),
                'stage_not_extremely_weak': stage_strength['stage_level'] != '极弱',
            },
            'month_pattern': {'month_hidden_entry_exists': bool(pillars[1]['hidden_stems']),
                              'all_prior_layers_excluded': None},
        }
    layers = []
    for index, (key, name, requirements) in enumerate(LAYERS):
        status = ('excluded_by_no_pair' if index == 0 and five_he['status'] == 'no_candidate'
                  else 'stage_candidate' if index == 0 and transformation_probe and
                  transformation_probe['status'] == 'stage_candidate'
                  else 'awaiting_prerequisites')
        layers.append({'id': key, 'name': name, 'status': status,
                       'required': list(requirements),
                       'stage_checks': stage_checks.get(key),
                       'reason': ('无天干五合配对，旧化气格入口不成立。' if status == 'excluded_by_no_pair'
                                  else '受限环境阶段已满足旧化气入口阈值；仍需完整前序链与经历复核。' if status == 'stage_candidate'
                                  else '前序数值与旺衰／排除链尚未全部复核，不能执行旧判定。')})

    follow_weak_stage = (_follow_weak_stage(pillars, environment, stage_strength)
                         if stage_strength['inputs'] is not None else None)
    selection = evaluate_selection(
        pillars, branch_replay or {}, five_he, environment,
        stage_strength, follow_weak_stage)
    if selection['status'] == 'calculated_selection':
        by_id = {row['id']: row for row in selection['layers']}
        for layer in layers:
            selected = by_id[layer['id']]
            layer['status'] = selected['status']
            layer['stage_checks'] = selected.get('gates') or (
                selected['result']['evidence'].get('gates')
                if selected['result'] and isinstance(selected['result']['evidence'], dict)
                else None)
            layer['reason'] = ('前层非假格已命中，本层不在该路径继续取格。'
                               if selected['status'] == 'not_reached' else
                               '旧规则入口命中，是否采用仍按条件路径核验。'
                               if selected['result'] else
                               '已按旧规则入口核对，当前层未命中。')
    conditional = []
    for candidate in five_he.get('candidates', []):
        if 'day' not in candidate['pillars']:
            continue
        target = candidate['target_element']
        pattern = f'化{target}格'
        conditional.append(_conditional_pattern(pattern, day, month, stage_strength, environment))
    scenarios = []
    if transformation_probe and transformation_probe['status'] == 'stage_candidate':
        scenarios.append({'id': 'transformation_accepted', 'assumptions': ['化气阶段候选成立'],
                          'pattern': transformation_probe['pattern_if_confirmed'],
                          'purity': transformation_probe['purity_if_final'],
                          'basis': '受限环境阶段与日干五合', 'decision': 'conditional_only'})
    if follow_weak_stage and follow_weak_stage['status'] == 'stage_candidate':
        scenarios.append({'id': 'follow_weak_accepted',
                          'assumptions': (['化气候选不成立'] if scenarios else []) + ['从弱阶段候选成立'],
                          'pattern': follow_weak_stage['pattern_if_confirmed'],
                          'purity': follow_weak_stage['purity_if_final'],
                          'basis': '旧结构破格权重与从格比例顺序的受限阶段复算',
                          'decision': 'conditional_only'})
    month_entry = _month_entry(pillars)
    if month_entry['candidates'] and not month_entry['requires_final_scores']:
        selected = max(month_entry['candidates'], key=lambda item: item['structural_weight'])
        month_pattern = ZHENGGE.get(selected['ten_god'])
        if month_pattern:
            scenarios.append({'id': 'ordinary_month_pattern',
                              'assumptions': [f"{row['pattern']}候选不成立" for row in scenarios] +
                                             ['其他前序特殊格局不成立'],
                              'pattern': month_pattern, 'purity': None,
                              'basis': '月令透藏结构权重；前五层排除仍待复核',
                              'decision': 'conditional_only'})
    if selection['status'] == 'calculated_selection':
        scenario_ids = {'transformation': 'transformation_accepted',
                        'dominant': 'dominant_accepted',
                        'follow_strong': 'follow_strong_accepted',
                        'follow_weak': 'follow_weak_accepted',
                        'lu_ren': 'lu_ren_pattern',
                        'month_pattern': 'ordinary_month_pattern'}
        scenarios = [{'id': scenario_ids[path['id']],
                      'assumptions': path['assumptions'],
                      'pattern': path['pattern'], 'purity': path['purity'],
                      'basis': '旧六层顺序、完整旺衰与环境余额；入口证据见 selection',
                      'decision': path['decision'],
                      'entry_evidence': path['evidence']}
                     for path in selection['paths']]
    for scenario in scenarios:
        pattern = scenario['pattern']
        scenario['conditional_evidence'] = _conditional_pattern(
            pattern, day, month, stage_strength, environment)
        scenario['useful_stem'] = select_useful_stem(
            pillars, reverse_pass or {}, scenario['conditional_evidence']['conditional_roles'])
        scenario['auspicious_combinations'] = combinations(
            pattern, pillars, stage_strength, environment, first_pass,
            reverse_pass, visible_pass)
        scenario['seasonal_results'] = [rule['stage_assessment'] for rule in
                                        scenario['conditional_evidence']['rules']]
        if not scenario['seasonal_results']:
            scenario['seasonal_results'] = [{
                'status': 'not_covered',
                'reason': scenario['conditional_evidence']['reason']}]
        scenario['uncovered_items'] = [
            *(f"逐干取用：{scenario['useful_stem']['reason']}" for _ in [0]
              if scenario['useful_stem']['status'] != 'conditional_selected'),
            *(f"吉凶条件：{term}" for term in
              scenario['auspicious_combinations']['uncovered_conditions']),
            *(f"调候：{row['reason']}" for row in scenario['seasonal_results']
              if row['status'] == 'not_covered'),
        ]
        scenario['favorable_elements'] = None
        scenario['limitation'] = ('本路径按旧入口、逐干正余额和配置计算；吉凶含未覆盖条件时不作最终匹配。'
                                  '首条为默认结果，后续路径供用户主动切换。')
    selected_stem = (scenarios[0]['useful_stem']['selected'] if scenarios and
                     scenarios[0]['useful_stem']['status'] == 'conditional_selected' else None)
    return {'version': VERSION, 'status': 'calculated_pattern_entries' if
            selection['status'] == 'calculated_selection' else 'conditional_evidence_only',
            'strength': {'status': stage_strength['status'], 'required': list(STRENGTH_INPUTS),
                         'reason': stage_strength['reason'],
                         'stage_probe': stage_strength},
            'selection': selection,
            'layers': layers, 'transformation_probe': transformation_probe,
            'follow_weak_probe': follow_weak_probe, 'follow_weak_stage': follow_weak_stage,
            'month_entry': month_entry, 'seasonal': conditional, 'scenarios': scenarios,
            'source_stage': environment['status'],
            'final_pattern': selection.get('final_pattern'),
            'resolution': selection.get('resolution', 'unavailable'),
            'selected_useful_stem': selected_stem,
            'favorable_elements': None}
