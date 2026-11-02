"""Traceable initial weights and isolated month formula, without intervening events.

This is a partial score snapshot. It deliberately excludes interactions,
sheng-ke redistribution, strength levels, patterns and useful elements.
"""
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from lunar_python.util import LunarUtil
from astral_nexus_mcp.engines.birth_time import CalculationError

VERSION = 'bazi-strength-partial-1'
FIVE = '木火土金水'
STEMS = set(LunarUtil.WU_XING_GAN)
BRANCHES = set(LunarUtil.ZHI_HIDE_GAN)
QI_KEYS = {'本气': 'main_qi', '中气': 'middle_qi', '余气': 'remaining_qi'}
RULES = json.loads((Path(__file__).parent / 'data' / 'bazi_scoring_v1.json').read_text())


def _validate_rules():
    if set(RULES['stem_base_weight']) != set(FIVE):
        raise ValueError('Invalid stem base weights')
    if any(set(RULES[key]) != BRANCHES for key in ('branch_qi_type', 'branch_qi_weight', 'month_stem_ratio')):
        raise ValueError('Incomplete branch/month weight table')
    for branch in BRANCHES:
        if set(RULES['branch_qi_type'][branch]) != set(LunarUtil.ZHI_HIDE_GAN[branch]):
            raise ValueError(f'Invalid qi types for {branch}')
        if set(RULES['branch_qi_weight'][branch]) != set(QI_KEYS.values()):
            raise ValueError(f'Invalid qi weights for {branch}')
        if set(RULES['month_stem_ratio'][branch]) != STEMS:
            raise ValueError(f'Invalid month ratios for {branch}')
        if any(Decimal(str(value)) <= 0 for value in RULES['month_stem_ratio'][branch].values()):
            raise ValueError(f'Nonpositive month ratio for {branch}')


_validate_rules()


def _two(value):
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN))


def calculate_partial(pillars: list[dict]):
    """Return initial weights and an isolated month adjustment with full trace."""
    try:
        if len(pillars) != 4 or [p['id'] for p in pillars] != ['year', 'month', 'day', 'hour']:
            raise ValueError('pillar order')
        month_branch = pillars[1]['branch']
        ratios = RULES['month_stem_ratio'][month_branch]
        components = []
        for pillar in pillars:
            stem, branch = pillar['stem'], pillar['branch']
            if stem not in STEMS or branch not in BRANCHES or pillar['gan_zhi'] != stem + branch:
                raise ValueError('invalid pillar')
            if set(h['stem'] for h in pillar['hidden_stems']) != set(LunarUtil.ZHI_HIDE_GAN[branch]):
                raise ValueError('invalid hidden stems')
            values = [(stem, 'visible', None, Decimal(str(RULES['stem_base_weight'][LunarUtil.WU_XING_GAN[stem]])))]
            for hidden in pillar['hidden_stems']:
                hidden_stem = hidden['stem']
                qi = RULES['branch_qi_type'][branch][hidden_stem]
                values.append((hidden_stem, 'hidden', qi,
                               Decimal(str(RULES['branch_qi_weight'][branch][QI_KEYS[qi]]))))
            for item_stem, position, qi, base in values:
                raw = Decimal(str(ratios[item_stem]))
                applied = max(Decimal('0.5'), min(Decimal('2.5'), Decimal('1') + (raw - 1) * Decimal('0.5')))
                components.append({'pillar': pillar['id'], 'stem': item_stem, 'branch': branch if position == 'hidden' else None,
                                   'position': position, 'qi': qi, 'element': LunarUtil.WU_XING_GAN[item_stem],
                                   'base': _two(base), 'month_raw_ratio': float(raw),
                                   'applied_ratio': float(applied), 'adjusted': _two(base * applied)})
        before = {element: round(sum(c['base'] for c in components if c['element'] == element), 2) for element in FIVE}
        after = {element: round(sum(c['adjusted'] for c in components if c['element'] == element), 2) for element in FIVE}
        return {'version': VERSION, 'scope': 'isolated_initial_weights_and_month_formula_without_intervening_events',
                'month_branch': month_branch, 'formula': 'adjusted = round(base × clamp(1 + (month_raw_ratio − 1) × 0.5, 0.5, 2.5), 2)',
                'components': components, 'totals_before': before, 'totals_after': after,
                'excluded': ['合冲刑害及会局', '生克分配', '根气强弱等级', '日主旺衰等级', '格局判定与最终取用']}
    except (KeyError, TypeError, ValueError) as exc:
        raise CalculationError('INVALID_CHART_REPORT', '四柱与基础力量规则表不一致') from exc
