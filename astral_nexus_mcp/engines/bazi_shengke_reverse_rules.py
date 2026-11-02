"""Reviewed active-hidden-qi-to-visible grades from legacy shengke_config.

The legacy callable table is used only by regression tests, never at runtime.
"""
from astral_nexus_mcp.engines.bazi_shengke_reverse_probe import RULES, YANG


def calculate(actor_score, target_score, global_ratio, current_ratio,
              relation, actor_stem, target_stem, target_has_root, qi='本气'):
    if qi not in ('本气', '中气', '余气'):
        raise ValueError('unknown hidden stem qi')
    thresholds = {
        '本气': {'virtual': 3., 'strong_gen_root': 1.2, 'strong_gen': 1.8,
                 'medium_gen_root': .8, 'medium_gen': 1.2, 'weak_gen': .3,
                 'reverse': .2, 'strong_control': 1.5, 'medium_control': .8,
                 'weak_control': .2},
        '中气': {'virtual': 4., 'strong_gen_root': 1.8, 'strong_gen': 2.7,
                 'medium_gen_root': 1.2, 'medium_gen': 1.8, 'weak_gen': .45,
                 'reverse': .1, 'strong_control': 2., 'medium_control': 1.2,
                 'weak_control': .1},
        '余气': {'virtual': 5., 'strong_gen_root': 2.4, 'strong_gen': 3.6,
                 'medium_gen_root': 1.6, 'medium_gen': 2.4, 'weak_gen': .6,
                 'reverse': .05, 'strong_control': 2.5, 'medium_control': 1.5,
                 'weak_control': .05},
    }[qi]
    rooted = actor_score > 0 or target_has_root
    if relation == '生':
        if global_ratio >= 3 and current_ratio >= thresholds['virtual']:
            level = '虚不受生'
        elif (rooted and global_ratio >= 1 and current_ratio >= thresholds['strong_gen_root']) or (global_ratio >= 1.5 and current_ratio >= thresholds['strong_gen']):
            level = '强生'
        elif (rooted and global_ratio >= .8 and current_ratio >= thresholds['medium_gen_root']) or (global_ratio >= 1.2 and current_ratio >= thresholds['medium_gen']):
            level = '中生'
        elif (global_ratio > .3 and current_ratio >= thresholds['weak_gen']) or (rooted and global_ratio > .1 and current_ratio > .1):
            level = '弱生'
        else:
            level = '不生'
    elif relation == '克':
        if global_ratio <= .2 and current_ratio < thresholds['reverse']:
            level = '反克'
        elif global_ratio >= 2 and current_ratio >= thresholds['strong_control']:
            level = '强克'
        elif global_ratio < 2 and current_ratio >= thresholds['medium_control']:
            level = '中克'
        elif global_ratio < 1.2 and current_ratio >= thresholds['weak_control']:
            level = '弱克'
        else:
            level = '不克'
    else:
        raise ValueError('unknown relation')
    min_ratio = min(global_ratio, current_ratio)
    qi_factor = {'本气': 1., '中气': .6, '余气': .4}[qi]
    different = ((actor_stem in YANG) != (target_stem in YANG) and
                 global_ratio > .8 and current_ratio > .8)
    polarity = (1. if different else .8) if relation == '生' else (.6 if different else 1.)
    if level in ('不生', '不克'):
        return {'level': level, 'delta': 0., 'hidden_change': 0.,
                'visible_change': 0., 'polarity_coefficient': polarity}
    if level == '虚不受生':
        raw = -.1 - .4 * (min(10., max(3., min_ratio)) - 3.) / 7.
        coefficient = abs(max(-.5, min(-.1, raw * qi_factor if qi != '本气' else raw)))
        hidden_ratio, visible_ratio = -.5, -.8
    elif level == '反克':
        raw = -.2 - .6 * (.6 - min_ratio)
        coefficient = abs(max(-.5, min(-.2, raw * qi_factor if qi != '本气' else raw)))
        hidden_ratio, visible_ratio = -.8, .6 * .8
    else:
        rule = RULES['normal_levels'][relation][level]
        coefficient = rule['coefficient'] * qi_factor
        hidden_ratio = rule['hidden_delta_ratio']
        visible_ratio = rule['visible_delta_ratio'] * RULES['visible_loss']
    delta = min(actor_score, target_score) * coefficient * polarity * RULES['common_adjustment']
    return {'level': level, 'delta': delta,
            'hidden_change': delta * hidden_ratio,
            'visible_change': delta * visible_ratio,
            'polarity_coefficient': polarity}
