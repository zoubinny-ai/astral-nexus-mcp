"""Reviewed visible-to-active-hidden-qi calculation from the legacy rule order."""
from astral_nexus_mcp.engines.bazi_shengke_probe import RULES, YANG, _normal_level


def calculate(actor_score, target_score, global_ratio, current_ratio,
              relation, actor_stem, target_stem, actor_has_root, target_has_root,
              qi='本气'):
    if qi not in ('本气', '中气', '余气'):
        raise ValueError('unknown hidden stem qi')
    thresholds = {
        '本气': {'abnormal': .3, 'strong_gen': 1.8, 'medium_gen': 1.2,
                 'weak_gen': .3, 'strong_control_root': 1., 'strong_control': 1.5,
                 'medium_control_root': .5, 'medium_control': .8,
                 'weak_control_root': .1, 'weak_control': .2, 'reverse': .2},
        '中气': {'abnormal': .25, 'strong_gen': 2.7, 'medium_gen': 1.8,
                 'weak_gen': .45, 'strong_control_root': 1.5, 'strong_control': 2.,
                 'medium_control_root': .8, 'medium_control': 1.2,
                 'weak_control_root': .05, 'weak_control': .1, 'reverse': .1},
        '余气': {'abnormal': .15, 'strong_gen': 3.6, 'medium_gen': 2.4,
                 'weak_gen': .6, 'strong_control_root': 2., 'strong_control': 2.5,
                 'medium_control_root': 1., 'medium_control': 1.5,
                 'weak_control_root': .02, 'weak_control': .05, 'reverse': .05},
    }[qi]
    rooted = actor_has_root or target_has_root
    if relation == '生':
        if global_ratio >= 1.5 and current_ratio >= thresholds['strong_gen']:
            level = '强生'
        elif global_ratio >= 1.2 and current_ratio >= thresholds['medium_gen']:
            level = '中生'
        elif (global_ratio > .3 and
              (current_ratio > thresholds['weak_gen'] if qi == '本气' else
               current_ratio >= thresholds['weak_gen'])) or (
                rooted and global_ratio > .1 and current_ratio > .1):
            level = '弱生'
        else:
            level = None
    elif relation == '克':
        if (rooted and global_ratio >= 1.5 and current_ratio >= thresholds['strong_control_root']) or (
                global_ratio >= 2 and current_ratio >= thresholds['strong_control']):
            level = '强克'
        elif (rooted and global_ratio < 2.5 and current_ratio >= thresholds['medium_control_root']) or (
                global_ratio < 2 and current_ratio >= thresholds['medium_control']):
            level = '中克'
        elif (rooted and global_ratio < 1.5 and current_ratio >= thresholds['weak_control_root']) or (
                global_ratio < 1.2 and current_ratio >= thresholds['weak_control']):
            level = '弱克'
        else:
            level = None
    else:
        raise ValueError('unknown relation')
    if relation == '生':
        if not actor_has_root and global_ratio <= .3 and current_ratio <= thresholds['abnormal']:
            level = '泄过为克'
        elif not target_has_root and global_ratio >= 3 and current_ratio >= {
                '本气': 3., '中气': 4., '余气': 5.}[qi]:
            level = '虚不受生'
    elif relation == '克' and global_ratio <= .2 and current_ratio < thresholds['reverse']:
        level = '反克'
    if level is None:
        level = '不生' if relation == '生' else '不克'
    different = ((actor_stem in YANG) != (target_stem in YANG) and
                 global_ratio > .8 and current_ratio > .8)
    polarity = (1. if different else .8) if relation == '生' else (.6 if different else 1.)
    if level in ('不生', '不克'):
        return {'level': level, 'delta': 0., 'actor_change': 0.,
                'target_change': 0., 'polarity_coefficient': polarity}
    min_ratio = min(global_ratio, current_ratio)
    qi_factor = {'本气': 1., '中气': .6, '余气': .4}[qi]
    if level == '泄过为克':
        raw = -.1 - .3 * (.3 - min_ratio) / .3
        coefficient = abs(max(-.5, min(-.1, raw * qi_factor if qi != '本气' else raw)))
        actor_ratio, target_ratio = -1., .8
        loss = 1.
    elif level == '虚不受生':
        raw = -.1 - .4 * (min(10., max(3., min_ratio)) - 3.) / 7.
        coefficient = abs(max(-.5, min(-.1, raw * qi_factor if qi != '本气' else raw)))
        actor_ratio, target_ratio = -.5, -1.
        loss = .8
    elif level == '反克':
        raw = -.2 - .6 * (.6 - min_ratio)
        coefficient = abs(max(-.5, min(-.2, raw * qi_factor if qi != '本气' else raw)))
        actor_ratio, target_ratio = -.8, .6
        loss = .8
    else:
        rule = RULES['normal_levels'][relation][level]
        coefficient = rule['coefficient'] * qi_factor
        actor_ratio, target_ratio = rule['actor_delta_ratio'], rule['target_delta_ratio']
        loss = RULES['actor_loss']
    delta = min(actor_score, target_score) * coefficient * polarity * RULES['common_adjustment']
    return {'level': level, 'delta': delta,
            'actor_change': delta * actor_ratio * loss,
            'target_change': delta * target_ratio,
            'polarity_coefficient': polarity}
