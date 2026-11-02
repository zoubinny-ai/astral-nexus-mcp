"""Auditable observations for Bazi review; never decides a pattern or useful element."""
from collections import Counter
from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.birth_time import CalculationError
from astral_nexus_mcp.engines.bazi_strength import RULES, calculate_partial
from astral_nexus_mcp.engines.bazi_interactions import audit as audit_interactions
from astral_nexus_mcp.engines.bazi_kongwang import audit as audit_kongwang
from astral_nexus_mcp.engines.bazi_group_probe import audit as audit_group, replay as replay_group
from astral_nexus_mcp.engines.bazi_group_branch_replay import replay as replay_group_branch
from astral_nexus_mcp.engines.bazi_group_activation import (audit as audit_group_activation,
                                           first_main_probe, first_pass as replay_group_first_pass)
from astral_nexus_mcp.engines.bazi_group_reverse_pass import replay as replay_group_reverse
from astral_nexus_mcp.engines.bazi_branch_replay import replay as replay_branches
from astral_nexus_mcp.engines.bazi_five_he import review as review_five_he
from astral_nexus_mcp.engines.bazi_life_stages import replay as replay_life_stages
from astral_nexus_mcp.engines.bazi_month_replay import replay as replay_month
from astral_nexus_mcp.engines.bazi_tonggen_replay import replay as replay_tonggen
from astral_nexus_mcp.engines.bazi_shengke_probe import probe as probe_shengke
from astral_nexus_mcp.engines.bazi_shengke_first_pass import replay as replay_shengke_first_pass
from astral_nexus_mcp.engines.bazi_shengke_reverse_probe import probe as probe_shengke_reverse
from astral_nexus_mcp.engines.bazi_shengke_reverse_pass import replay as replay_shengke_reverse_pass
from astral_nexus_mcp.engines.bazi_shengke_priority_inputs import audit as audit_shengke_priority_inputs
from astral_nexus_mcp.engines.bazi_shengke_tongguan_audit import audit as audit_shengke_tongguan
from astral_nexus_mcp.engines.bazi_shengke_zhihua_audit import audit as audit_shengke_zhihua
from astral_nexus_mcp.engines.bazi_shengke_hehua_event_audit import audit as audit_shengke_hehua_event
from astral_nexus_mcp.engines.bazi_shengke_priority_review import audit as audit_shengke_priority_review
from astral_nexus_mcp.engines.bazi_shengke_allocation_plan import audit as audit_shengke_allocation_plan
from astral_nexus_mcp.engines.bazi_shengke_allocation_ledger import replay as replay_shengke_allocation_ledger
from astral_nexus_mcp.engines.bazi_shengke_visible_probe import replay as replay_shengke_visible_probe
from astral_nexus_mcp.engines.bazi_shengke_visible_pass import replay as replay_shengke_visible_pass
from astral_nexus_mcp.engines.bazi_environment import audit as audit_environment, replay as replay_environment
from astral_nexus_mcp.engines.bazi_pattern_review import review as review_pattern_inputs

ENGINE_VERSION = 'bazi-evidence-51'
METHODS = ('ziping', 'ditiansui', 'tiaohou', 'mangpai')
STEM_COMBINATIONS = {
    frozenset(('甲', '己')): '土', frozenset(('乙', '庚')): '金',
    frozenset(('丙', '辛')): '水', frozenset(('丁', '壬')): '木',
    frozenset(('戊', '癸')): '火',
}
SEASONS = {
    **dict.fromkeys('寅卯辰', '春'), **dict.fromkeys('巳午未', '夏'),
    **dict.fromkeys('申酉戌', '秋'), **dict.fromkeys('亥子丑', '冬'),
}
PILLAR_NAMES = {'year': '年', 'month': '月', 'hour': '时'}
PRODUCER_OF = {'木': '水', '火': '木', '土': '火', '金': '土', '水': '金'}
GENERATES = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
CONTROLS = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
FIVE_HE_STAGE_LABELS = {
    'no_candidate': '无五合配对',
    'not_covered': '前序或五合条件尚未覆盖',
    'guard_failed': '已审核门槛阻止作用',
    'isolated_partial_stage': '单一部分作用已受限复算',
    'isolated_complete_stage': '完整五合作用已受限复算',
}


def _fact(rule_id, text, source, limitation):
    return {'rule_id': rule_id, 'fact': text, 'source': source, 'limitation': limitation}


def _pillars(chart):
    try:
        rows = chart['pillars']
        if len(rows) != 4 or [p['id'] for p in rows] != ['year', 'month', 'day', 'hour']:
            raise ValueError('pillar order')
        for row in rows:
            stem, branch = row['stem'], row['branch']
            if row['gan_zhi'] != stem + branch or stem not in LunarUtil.WU_XING_GAN or branch not in LunarUtil.ZHI_HIDE_GAN:
                raise ValueError('pillar contents')
            if [h['stem'] for h in row['hidden_stems']] != LunarUtil.ZHI_HIDE_GAN[branch]:
                raise ValueError('hidden stems')
        if chart['day_master'] != rows[2]['stem']:
            raise ValueError('day master')
        return rows
    except (KeyError, TypeError, ValueError) as exc:
        raise CalculationError('INVALID_CHART_REPORT', '八字报告缺少可核对的四柱与藏干') from exc


def extract(chart: dict, fortune: dict | None = None):
    """Extract exact facts; reference labels and final assessments are not inputs."""
    rows = _pillars(chart)
    partial = calculate_partial(rows)
    interactions = audit_interactions(rows, partial)
    group_audit = audit_group(rows, partial, interactions)
    group_probe = replay_group(rows, partial, interactions, group_audit)
    group_branch_replay = replay_group_branch(rows, partial, interactions, group_audit, group_probe)
    group_activation = audit_group_activation(
        rows, partial, interactions, group_audit, group_probe, group_branch_replay)
    group_five_he = review_five_he(rows, group_branch_replay)
    group_life_stages = replay_life_stages(rows, group_branch_replay, group_five_he)
    group_month_replay = replay_month(rows, group_branch_replay, group_life_stages)
    group_tonggen_replay = replay_tonggen(rows, group_month_replay)
    group_first_probe = first_main_probe(rows, group_activation, group_tonggen_replay)
    group_first_pass = replay_group_first_pass(rows, group_activation, group_tonggen_replay)
    group_reverse_pass = replay_group_reverse(
        rows, group_activation, group_tonggen_replay, group_first_pass)
    group_priority_inputs = audit_shengke_priority_inputs(rows, group_reverse_pass)
    group_tongguan = audit_shengke_tongguan(rows, group_reverse_pass, group_priority_inputs)
    group_zhihua = audit_shengke_zhihua(
        rows, group_reverse_pass, group_priority_inputs, group_tongguan)
    group_events = audit_shengke_hehua_event(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua)
    group_priority = audit_shengke_priority_review(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua, group_events)
    group_plan = audit_shengke_allocation_plan(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua, group_events, group_priority)
    group_ledger = replay_shengke_allocation_ledger(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua, group_events, group_priority,
        group_plan)
    group_visible_probe = replay_shengke_visible_probe(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua, group_events, group_priority,
        group_plan, group_ledger)
    group_visible_pass = replay_shengke_visible_pass(
        rows, group_branch_replay, group_five_he, group_reverse_pass,
        group_priority_inputs, group_tongguan, group_zhihua, group_events, group_priority,
        group_plan, group_ledger, group_visible_probe)
    group_environment_audit = audit_environment(rows, group_visible_pass)
    group_environment_replay = replay_environment(
        rows, group_visible_pass, group_environment_audit)
    kongwang_audit = audit_kongwang(rows, interactions)
    branch_replay = replay_branches(rows, partial, interactions)
    five_he = review_five_he(rows, branch_replay)
    five_he_stage_label = FIVE_HE_STAGE_LABELS[five_he['status']]
    life_stages = replay_life_stages(rows, branch_replay, five_he)
    month_replay = replay_month(rows, branch_replay, life_stages)
    tonggen_replay = replay_tonggen(rows, month_replay)
    shengke_probe = probe_shengke(rows, tonggen_replay)
    shengke_first_pass = replay_shengke_first_pass(rows, tonggen_replay, branch_replay)
    shengke_reverse_probe = probe_shengke_reverse(rows, shengke_first_pass)
    shengke_reverse_pass = replay_shengke_reverse_pass(rows, shengke_first_pass, branch_replay)
    shengke_priority_inputs = audit_shengke_priority_inputs(rows, shengke_reverse_pass)
    shengke_tongguan_audit = audit_shengke_tongguan(rows, shengke_reverse_pass, shengke_priority_inputs)
    shengke_zhihua_audit = audit_shengke_zhihua(
        rows, shengke_reverse_pass, shengke_priority_inputs, shengke_tongguan_audit)
    shengke_hehua_event_audit = audit_shengke_hehua_event(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit)
    shengke_priority_review = audit_shengke_priority_review(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit,
        shengke_hehua_event_audit)
    shengke_allocation_plan = audit_shengke_allocation_plan(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit,
        shengke_hehua_event_audit, shengke_priority_review)
    shengke_allocation_ledger = replay_shengke_allocation_ledger(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit,
        shengke_hehua_event_audit, shengke_priority_review, shengke_allocation_plan)
    shengke_visible_probe = replay_shengke_visible_probe(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit,
        shengke_hehua_event_audit, shengke_priority_review, shengke_allocation_plan,
        shengke_allocation_ledger)
    shengke_visible_pass = replay_shengke_visible_pass(
        rows, branch_replay, five_he, shengke_reverse_pass,
        shengke_priority_inputs, shengke_tongguan_audit, shengke_zhihua_audit,
        shengke_hehua_event_audit, shengke_priority_review, shengke_allocation_plan,
        shengke_allocation_ledger, shengke_visible_probe)
    environment_audit = audit_environment(rows, shengke_visible_pass)
    environment_replay = replay_environment(rows, shengke_visible_pass, environment_audit)
    pattern_review = review_pattern_inputs(
        rows, five_he=five_he,
        environment=environment_replay,
        group_audit=group_audit, branch_replay=branch_replay,
        reverse_pass=shengke_reverse_pass, first_pass=shengke_first_pass,
        visible_pass=shengke_visible_pass)
    day_stem = rows[2]['stem']
    month = rows[1]
    visible = Counter(LunarUtil.WU_XING_GAN[p['stem']] for p in rows)
    hidden = Counter(LunarUtil.WU_XING_GAN[h['stem']] for p in rows for h in p['hidden_stems'])
    day_element = LunarUtil.WU_XING_GAN[day_stem]
    root_branches = [p['branch'] for p in rows if any(
        LunarUtil.WU_XING_GAN[h['stem']] == day_element for h in p['hidden_stems'])]
    root_components = [c for c in partial['components'] if c['position'] == 'hidden' and c['element'] == day_element]
    visible_components = [c for c in partial['components'] if c['position'] == 'visible' and c['element'] == day_element]
    visible_baseline = round(sum(c['adjusted'] for c in visible_components), 2)
    hidden_baseline = round(sum(c['adjusted'] for c in root_components), 2)
    total_partial = sum(partial['totals_after'].values())
    month_main_stem = next(stem for stem, qi in RULES['branch_qi_type'][month['branch']].items() if qi == '本气')
    month_main_element = LunarUtil.WU_XING_GAN[month_main_stem]
    combinations = []
    for index in (0, 1, 3):
        other = rows[index]
        candidate = STEM_COMBINATIONS.get(frozenset((day_stem, other['stem'])))
        if candidate:
            producer = PRODUCER_OF[candidate]
            distance = abs(index - 2)
            mid_stems = [rows[i]['stem'] for i in range(min(index, 2) + 1, max(index, 2))]
            mid_element = LunarUtil.WU_XING_GAN[mid_stems[0]] if distance == 2 else None
            left_element, right_element = (LunarUtil.WU_XING_GAN[other['stem']], day_element)
            separated_chain = (GENERATES[left_element] == mid_element and GENERATES[mid_element] == right_element) or (
                GENERATES[right_element] == mid_element and GENERATES[mid_element] == left_element) if distance == 2 else None
            combinations.append({'with_pillar': other['id'], 'pair': day_stem + other['stem'],
                                 'possible_element': candidate, 'adjacent': distance == 1,
                                 'distance_eligible': distance <= 2,
                                 'intervening_stems': mid_stems,
                                 'ends_control_each_other': CONTROLS[left_element] == right_element or CONTROLS[right_element] == left_element,
                                 'separated_generating_chain': separated_chain,
                                 'month_main_qi_element': month_main_element,
                                 'month_main_qi_matches': month_main_element == candidate,
                                 'exposed_candidate_stems': [p['stem'] for p in rows if LunarUtil.WU_XING_GAN[p['stem']] == candidate],
                                 'partial_candidate_share': round(partial['totals_after'][candidate] / total_partial * 100, 2),
                                 'partial_producer_element': producer,
                                 'partial_producer_share': round(partial['totals_after'][producer] / total_partial * 100, 2)})
    sections = {
        'ziping': [
            _fact('ZP-01', f"日主{day_stem}，月支{month['branch']}，月支藏干{'、'.join(h['stem'] for h in month['hidden_stems'])}。",
                  'chart.pillars.day/month', '月令和藏干只是取格输入，不能单独确定格局。'),
            _fact('ZP-02', f"与日主同五行（{day_element}）的藏干{'见于' + '、'.join(root_branches) + '支' if root_branches else '未见于四支'}。",
                  'chart.pillars[*].hidden_stems', '同五行藏干的位置并非旺衰评分；未校验根气强弱、刑冲合会。'),
            _fact('ZP-04', f"日主同五行（{day_element}）的独立月令基线：透干 {visible_baseline:.2f} + 藏干 {hidden_baseline:.2f} = {partial['totals_after'][day_element]:.2f}。{'四支没有同五行藏干，藏干子项因此为 0；' if not root_components else ''}逐项原值和系数见基础力量表。",
                  'partial_strength.components/totals_after', '只是未计入地支关系、生克等前序事件的独立基线；藏干子项为 0 不表示该五行总分为 0，也不能据此判断通根、旺衰或最终取用。'),
            _fact('ZP-05', '旧取格按化气、专旺、从旺、从弱／从势、禄刃、月令正格依次审核；逐层命中与排除见六层账本。',
                  'pattern_review.selection.layers', '首条命中路径是默认计算结果；后续路径仅在主动切换时作为解读前提。'),
            _fact('ZP-06', '月令透藏结构候选：' + '、'.join(
                f"{item['hidden_qi']}{item['hidden_stem']}→{item['visible_stem'] or '本气回退'}（权重{item['structural_weight']:.1f}）"
                for item in pattern_review['month_entry']['candidates']) + '。',
                'pattern_review.month_entry', pattern_review['month_entry']['reason']),
        ],
        'ditiansui': [
            _fact('DT-01', '四柱天干五行出现次数：' + '、'.join(f'{e}{visible[e]}' for e in '木火土金水') + '。',
                  'chart.pillars[*].stem', '出现次数不代表五行力量或气势。'),
            _fact('DT-02', '四支藏干五行出现次数：' + '、'.join(f'{e}{hidden[e]}' for e in '木火土金水') + '。',
                  'chart.pillars[*].hidden_stems', '藏干未按月令、透干、根气等赋权，不能用次数判旺衰。'),
            _fact('DT-03', '透干与藏干经月令调整的部分权重：' + '、'.join(f"{e}{partial['totals_after'][e]:.2f}" for e in '木火土金水') + '。',
                  'partial_strength.totals_after', '尚无合冲刑害、生克分配和日主旺衰综合，不构成滴天髓气势结论。'),
        ],
        'tiaohou': [
            _fact('TH-01', f"月支{month['branch']}，按节令分组属于{SEASONS[month['branch']]}季。",
                  'chart.pillars.month.branch', '季节背景并非调候用神；寒暖燥湿与取用尚待审核。'),
        ],
        'mangpai': [],
    }
    strength_probe = pattern_review['strength']['stage_probe']
    selection = pattern_review['selection']
    if selection['status'] == 'calculated_selection':
        sections['ziping'].append(_fact(
            'ZP-10', '六层顺序取格路径：' + '；'.join(
                f"{'／'.join(row['assumptions']) + '后' if row['assumptions'] else ''}{row['purity'] or row['pattern']}"
                for row in selection['paths']) + '。',
            'pattern_review.selection.paths',
            '取格入口由完整旺衰和旧规则计算；首条为默认结果，真假格分支可切换。'))
    if strength_probe['status'] == 'calculated_strength':
        sections['ditiansui'].append(_fact(
            'DT-04', f"环境阶段日干占比 {strength_probe['inputs']['day_strength_percent']:.6f}%，旧旺衰第一维 {strength_probe['day_strength_component']:.6f}/20；生扶减克泄值 {strength_probe['inputs']['balance']:.6f}，第五维按旧下界截断得 {strength_probe['balance_component']:.6f}/8；月令日干比例 {strength_probe['inputs']['month_ratio']:.2f}，第七维配置评分 {strength_probe['month_component']:.6f}/12。",
            'pattern_review.strength.stage_probe',
            '完整环境余额和结构已对账；第五维的 0 是负值按旧公式截断，并非缺失填零；逐干取用见所选路径结果。'))
        if strength_probe['stage_score'] is not None:
            sections['ditiansui'].append(_fact(
                'DT-05', f"统一链八维旺衰合计 {strength_probe['stage_score']}，旧等级映射为{strength_probe['stage_level']}。",
                'pattern_review.strength.stage_probe.stage_components',
                '环境余额和同柱得生日支已对账；格局仍须依六层旧顺序判定，实际取用另审。'))
    transformation_probe = pattern_review['transformation_probe']
    if transformation_probe is not None:
        sections['ziping'].append(_fact(
            'ZP-08', f"旧化气入口阶段核对：{transformation_probe['pattern_if_confirmed']}方向占比 {transformation_probe['target_share']:.6f}%，生化神占比 {transformation_probe['producer_share']:.6f}%，门槛状态 {transformation_probe['status']}。",
            'pattern_review.transformation_probe', transformation_probe['limitation']))
    follow_weak_probe = pattern_review['follow_weak_probe']
    if follow_weak_probe is not None:
        sections['ziping'].append(_fact(
            'ZP-09', f"旧从格四项结构入口已逐项核对，不满足 {follow_weak_probe['unmet_count']} 项。",
            'pattern_review.follow_weak_probe', follow_weak_probe['limitation']))
    for item in pattern_review['seasonal']:
        if item['conditional_roles']:
            sections['ziping'].append(_fact(
                'ZP-07', f"若后续确认{item['pattern_if_confirmed']}，旧配置列格神{'、'.join(item['conditional_roles']['格神']) or '未列出'}、相神{'、'.join(item['conditional_roles']['相神']) or '未列出'}。",
                'pattern_review.seasonal.conditional_roles',
                '这是格局成立后的配置映射；尚未按逐干分数选择实际用神，不能直接当作本盘喜忌。'))
        for rule in item['rules']:
            sections['tiaohou'].append(_fact(
                'TH-02', f"若后续确认{item['pattern_if_confirmed']}，旧配置对{day_stem}日{month['branch']}月的{rule['type']}列出需求五行{rule['needed_element']}、参考天干{'、'.join(rule['stems'])}。",
                'pattern_review.seasonal', item['limitation']))
            stage = rule['stage_assessment']
            if stage['status'] == 'conditional_stage':
                sections['tiaohou'].append(_fact(
                    'TH-03', f"若确认{item['pattern_if_confirmed']}，{rule['type']}在受限环境阶段的需求强度 {stage['intensity']:.6f}，旧阈值对应{stage['level']}／{stage['climate_state']}，条件性评分 {stage['conditional_score']}。",
                    'pattern_review.seasonal.rules[*].stage_assessment', stage['reason']))
    for item in combinations:
        sections['ziping'].append(_fact(
            'ZP-03', f"日干与{PILLAR_NAMES[item['with_pillar']]}干构成{item['pair']}合，传统合化方向为{item['possible_element']}；两干{'相邻' if item['adjacent'] else '不相邻'}{'，中隔' + '、'.join(item['intervening_stems']) if item['intervening_stems'] else ''}。{'隔干形成相生链' if item['separated_generating_chain'] else '隔干未形成相生链' if item['separated_generating_chain'] is False else '无需隔干通关检查'}；月支本气{month_main_stem}属{month_main_element}；部分力量中{item['possible_element']}占{item['partial_candidate_share']:.2f}%、生{item['possible_element']}的{item['partial_producer_element']}占{item['partial_producer_share']:.2f}%。",
            f"chart.pillars.day/{item['with_pillar']}",
            f"占比仅来自独立透藏基线与月令调整；五合阶段：{five_he_stage_label}（{five_he['reason']}）。阶段分数不等于化气格判定，不能以旧阈值直接认定真化、假化或合而不化。"))
    if fortune is not None:
        try:
            if fortune['chart_utc'] != chart['utc'] or fortune['direction'] != chart['luck_direction']:
                raise ValueError('fortune mismatch')
            period_count = len(fortune['periods'])
            annual_count = len(fortune['annual'])
            if period_count != 8 or not annual_count:
                raise ValueError('fortune incomplete')
        except (KeyError, TypeError, ValueError) as exc:
            raise CalculationError('CHART_RULE_MISMATCH', '大运报告与四柱报告不匹配') from exc
        sections['mangpai'].append(_fact(
            'MP-01', f"已保存大运{'顺排' if fortune['direction'] == 'forward' else '逆排'}，含{period_count}步大运和{annual_count}个节气年；历史事件尚未填写。",
            'fortune.direction/periods/annual', '时间轴不是事件验证；须由用户提供过去关键年份及经历，不能自动推断应验。'))
    else:
        sections['mangpai'].append(_fact(
            'MP-00', '尚无关联的大运流年报告，历史事件也未填写。',
            'fortune report absent', '此处不能进行大运流年复核。'))
    triggers = []
    if combinations:
        triggers.append({'rule_id': 'DISPUTE-01', 'reason': f"日干出现五合候选；五合阶段：{five_he_stage_label}。化气格与最终取用仍需结合完整规则及经历复核。",
                         'evidence_rule_ids': ['ZP-01', 'ZP-02', 'ZP-03']})
    return {
        'engine_version': ENGINE_VERSION,
        'methods': [{'id': method, 'facts': sections[method]} for method in METHODS],
        'day_stem_combinations': combinations,
        'partial_strength': partial,
        'pattern_review': pattern_review,
        'interaction_audit': interactions,
        'group_audit': group_audit,
        'group_probe': group_probe,
        'group_branch_replay': group_branch_replay,
        'group_activation': group_activation,
        'group_pre_shengke': {
            'five_he': group_five_he,
            'life_stages': group_life_stages,
            'month': group_month_replay,
            'tonggen': group_tonggen_replay,
            'first_shengke_probe': group_first_probe,
            'first_shengke_pass': group_first_pass,
            'reverse_pass': group_reverse_pass,
            'priority_inputs': group_priority_inputs,
            'tongguan': group_tongguan,
            'zhihua': group_zhihua,
            'hehua_events': group_events,
            'priority': group_priority,
            'allocation_plan': group_plan,
            'allocation_ledger': group_ledger,
            'visible_probe': group_visible_probe,
            'visible_pass': group_visible_pass,
            'environment_audit': group_environment_audit,
            'environment_replay': group_environment_replay,
            'scope': '早期单组会合回归链，仅供与统一计算链对照；统一地支、生克、环境阶段是当前连续计算结果。',
        },
        'kongwang_audit': kongwang_audit,
        'branch_replay': branch_replay,
        'five_he_audit': five_he,
        'life_stages_audit': life_stages,
        'month_replay': month_replay,
        'tonggen_replay': tonggen_replay,
        'shengke_probe': shengke_probe,
        'shengke_first_pass': shengke_first_pass,
        'shengke_reverse_probe': shengke_reverse_probe,
        'shengke_reverse_pass': shengke_reverse_pass,
        'shengke_priority_inputs': shengke_priority_inputs,
        'shengke_tongguan_audit': shengke_tongguan_audit,
        'shengke_zhihua_audit': shengke_zhihua_audit,
        'shengke_hehua_event_audit': shengke_hehua_event_audit,
        'shengke_priority_review': shengke_priority_review,
        'shengke_allocation_plan': shengke_allocation_plan,
        'shengke_allocation_ledger': shengke_allocation_ledger,
        'shengke_visible_probe': shengke_visible_probe,
        'shengke_visible_pass': shengke_visible_pass,
        'environment_audit': environment_audit,
        'environment_replay': environment_replay,
        'dispute': {'status': 'needs_review' if pattern_review['resolution'] == 'calculated_with_alternatives'
                    else 'not_flagged', 'triggers': triggers,
                    'scope': '首条为默认结果；存在真假格分支时可选择后续路径，无须先确认。'},
        'final_pattern': pattern_review['final_pattern'],
        'selected_useful_stem': pattern_review['selected_useful_stem'],
        'favorable_elements': None,
    }
