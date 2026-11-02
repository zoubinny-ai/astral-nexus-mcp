"""Reviewed condition vocabulary from the old Jixiong checkers.

Relationship checks require completed, positive, ordered score events. A name
alone or the coexistence of two ten gods is not evidence of an applied action.
"""

import json
from pathlib import Path

from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES

VERSION = 'bazi-jixiong-predicates-2'
RELATIONS = json.loads((Path(__file__).parent / 'data' / 'bazi_jixiong_relations_v1.json').read_text())['rules']
CLASSES = {'比劫': ('比肩', '劫财'), '印星': ('正印', '偏印'),
           '官杀': ('正官', '七杀'), '食伤': ('食神', '伤官'),
           '财星': ('正财', '偏财')}
STRENGTH_LIMIT = {'比劫': 15, '印星': 15, '官杀': 15, '食伤': 15, '财星': 15}


def _is(god, category):
    return god in CLASSES.get(category, (category,))


def _events(pillars, first, reverse, visible):
    if [r.get('status') for r in (first, reverse, visible)] != [
            'isolated_first_pass', 'isolated_reverse_pass', 'isolated_visible_pass']:
        return None
    day = pillars[2]['stem']
    result = []
    for index, stage in enumerate((first, reverse, visible)):
        for event in stage['events']:
            if index == 0:
                actor, target = event['actor'], event['target']
                owner = other = event['pillar']
                actor_day, target_day = owner == 'day', False
            elif index == 1:
                actor, target = event['hidden_stem'], event['visible_stem']
                owner = other = event['pillar']
                actor_day, target_day = False, other == 'day'
            else:
                actor, target = event['actor_stem'], event['target_stem']
                owner, other = event['actor_pillar'], event['target_pillar']
                actor_day, target_day = owner == 'day', other == 'day'
            result.append({'relation': event['relation'],
                           'actor': LunarUtil.SHI_SHEN[day + actor],
                           'target': LunarUtil.SHI_SHEN[day + target],
                           'actor_day': actor_day, 'target_day': target_day,
                           'actor_pillar': owner, 'target_pillar': other,
                           'base_delta': event['base_delta'], 'stage': index})
    return result


class JixiongContext:
    def __init__(self, pillars, environment, first, reverse, visible):
        self.pillars = pillars
        self.visible = [p['stem_ten_god'] for p in pillars if p['id'] != 'day']
        self.main = []
        self.hidden = []
        for p in pillars:
            qi = RULES['branch_qi_type'][p['branch']]
            for h in p['hidden_stems']:
                self.hidden.append((h['ten_god'], qi[h['stem']]))
                if qi[h['stem']] == '本气':
                    self.main.append(h['ten_god'])
        self.events = _events(pillars, first, reverse, visible)
        self.scores = None
        if environment.get('status') == 'isolated_environment_stage':
            self.scores = {name: 0.0 for name in (*sum((list(g) for g in CLASSES.values()), []), '日主')}
            for row in environment['visible_balances_after'] + environment['hidden_balances_after']:
                god = ('日主' if row['pillar'] == 'day' and row in environment['visible_balances_after']
                       else LunarUtil.SHI_SHEN[pillars[2]['stem'] + row['stem']])
                self.scores[god] += row['score']
        self.total = sum(self.scores.values()) if self.scores else None

    def present(self, category):
        return any(_is(god, category) for god in self.visible)

    def rooted(self, category):
        weight = sum({'本气': 2.0, '中气': .45, '余气': .25}[qi]
                     for god, qi in self.hidden if _is(god, category))
        return weight >= .45

    def score(self, category):
        return sum(value for god, value in self.scores.items() if _is(god, category))

    def strong(self, category):
        if not self.scores or not self.total:
            return None
        score = self.score(category)
        threshold = STRENGTH_LIMIT.get(category, 12)
        return score >= threshold or score / self.total >= .2

    def class_very_strong(self, category):
        if not self.scores or not self.total:
            return None
        classes = {name: self.score(name) for name in CLASSES}
        total = sum(classes.values())
        if total <= 0:
            return None
        target = classes[category]
        same = classes['印星'] + classes['比劫']
        other = total - same
        ratio = same / other if other > 0 else float('inf')
        target_ratio = target / total
        points = (40 if target_ratio >= .4 else 30 if target_ratio >= .25 else
                  20 if target_ratio >= .2 else 15 if target_ratio >= .15 else 5)
        aligned = same / total if category in ('印星', '比劫') else other / total
        points += 30 if aligned >= .6 else 20 if aligned >= .4 else 15 if aligned >= .3 else 5
        if category in ('印星', '比劫'):
            points += 20 if ratio >= 1.2 else 15 if ratio >= .8 else 10 if ratio >= .6 else 5
        else:
            points += 20 if ratio <= .8 else 15 if ratio <= 1 else 10 if ratio <= 1.2 else 5
        points += 10 if target >= 30 else 8 if target >= 20 else 5 if target >= 10 else 2
        return points >= 80

    def relation(self, name):
        if self.events is None:
            return None, '生克三段事件尚未完整复算。'
        found = next(((kind, tokens) for kind, rules in RELATIONS.items()
                      for label, tokens in rules.items() if label == name), None)
        if name == '食伤制官杀':
            found = ('制', ['食伤', '官杀'])
        if found is None:
            return None, '旧静态关系表未定义此名称。'
        kind, tokens = found
        if name == '印星生日主':
            matched = next((event for event in self.events
                            if event['relation'] == '生' and event['base_delta'] > 0 and
                            _is(event['actor'], '印星') and event['target_day']), None)
            return (matched is not None,
                    '旧静态匹配器先命中印星生比劫，再在受方为日柱时补记印星生日主。')
        def matches(event, side, token):
            # The old ten-god mapping labels the day stem 比肩. Other “日主”
            # static names do not match it directly in the executable matcher.
            return False if token == '日主' else _is(event[side], token)
        def hits(a, b, relation):
            return [event for event in self.events if event['relation'] == relation and
                    event['base_delta'] > 0 and matches(event, 'actor', a) and
                    matches(event, 'target', b)]
        if kind == '通关' and len(tokens) >= 3:
            a, middle, b = tokens[:3]
            for first in hits(a, middle, '生'):
                for second in hits(middle, b, '生'):
                    if first['target_pillar'] == second['actor_pillar']:
                        return True, f'已作用的两段生关系在{first["target_pillar"]}柱承接。'
            return False, '完整事件账本无同柱承接的两段通关。'
        if len(tokens) < 2:
            return None, '旧关系缺少主体或客体。'
        a, b = tokens[:2]
        if kind == '化':
            matched = hits(b, a, '生')
        else:
            matched = hits(a, b, '克' if kind in ('克', '制') else '生')
        if matched:
            event = matched[0]
            return True, f'已作用{event["relation"]}关系：{event["actor_pillar"]}→{event["target_pillar"]}。'
        return False, '完整事件账本无对应已作用关系。'

    def predicate(self, term, *, kind):
        visible = self.visible
        if term.endswith('透干'):
            return self.present(term[:-2]), '旧透干检查器：四柱非日主天干。'
        if term.endswith(('有根', '无根')):
            absent = term.endswith('无根')
            category = term[:-2]
            value = self.rooted(category)
            if kind.startswith('poge') and absent:
                value = self.present(category) and not value
            return not value if absent and not kind.startswith('poge') else value, '旧藏干本／中／余气权重及 0.45 门槛。'
        if term == '财印相隔':
            return ((visible[0] in CLASSES['财星'] or visible[1] in CLASSES['财星']) and
                    visible[2] in CLASSES['印星']), '旧位置条件：年／月干财星、时干印星。'
        if term == '官杀紧贴日主':
            return visible[1] in CLASSES['官杀'] or visible[2] in CLASSES['官杀'], '旧位置条件：月干或时干官杀。'
        if term == '伤官当令':
            return self.main[1] == '伤官', '旧月支本气十神。'
        if term == '官杀混杂':
            return '正官' in visible and '七杀' in visible, '旧检查器：正官、七杀同透。'
        if term == '食神混局':
            return '食神' in visible and '伤官' in visible, '旧检查器：食神、伤官同透。'
        if term == '独官清贵':
            return visible.count('正官') == 1 and '七杀' not in visible, '旧检查器：一正官且无七杀透干。'
        if term in ('食伤混杂', '官杀清纯', '食伤清纯'):
            pair = ('正官', '七杀') if term.startswith('官杀') else ('食神', '伤官')
            both = all(god in visible for god in pair)
            return (both if term == '食伤混杂' else any(god in visible for god in pair) and not both), '按同类两十神透干纯杂核验。'
        if term == '比劫林力':
            return sum(_is(god, '比劫') for god in visible) >= 2, '旧破格检查器：比劫透干至少二处。'
        if term.endswith('林立'):
            category = term[:-2]
            gods = self.visible + self.main
            threshold = 3 if category == '比劫' else 4
            if kind.startswith('poge') and category == '官杀':
                gods, threshold = self.visible, 2
            return sum(_is(god, category) for god in gods) >= threshold, f'旧林立检查器计透干与本气，门槛{threshold}。'
        if term == '七杀无制化':
            checks = [self.relation(name)[0] for name in ('食神制杀', '食伤制杀', '印星化杀')]
            return (not any(checks) if all(value is not None for value in checks) else None), '旧破格条件：无食神／食伤制杀且无印星化杀。'
        if term == '比劫助身':
            return self.present('比劫'), '旧特殊静态关系：比劫透干助身。'
        if term == '食伤泄秀' and kind.startswith('poge'):
            return self.present('食伤'), '旧破格检查器对该词直接检查食伤透干。'
        if term.endswith(('强旺', '有力', '无力')):
            if term.endswith('强旺'):
                category = term[:-2]
                if kind.startswith('poge'):
                    value = self.class_very_strong('官杀' if category == '七杀' else category)
                else:
                    value = self.strong(category)
                if value is not None and category in ('正财', '偏财', '印星', '官杀', '财星', '七杀'):
                    value = value and self.present(category) and self.rooted(category)
            else:
                negative = term.endswith('无力')
                category = term[:-2]
                if kind.startswith('poge') and category in ('印星', '比劫'):
                    value = self.present(category) and not self.rooted(category)
                else:
                    value = self.strong('食伤' if category == '食神' else category)
                    if value is not None:
                        value = (not value if negative else value)
                        if category in ('正财', '偏财'):
                            value = value and self.present(category) and self.rooted(category)
                        if category == '食神' and negative:
                            value = value and self.present('食神')
            return value, '按旧十神分数／占比阈值及相应透干、根气门槛。'
        return self.relation(term)
