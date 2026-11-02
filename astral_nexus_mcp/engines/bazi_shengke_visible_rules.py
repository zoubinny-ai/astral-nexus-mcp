"""Audited visible-stem interaction levels from the legacy gan-gan table.

Source: score_analysis/shengke/shengke_config.py::SHENGKE_GAN_GAN_CONFIG
and score_analysis/shengke/shengke_radio.py::process_gan_gan_shengke.
No legacy module is imported at runtime.
"""

from math import isfinite

from astral_nexus_mcp.engines.bazi_shengke_probe import YANG


NORMAL = {
    '生': {'强生': (.7, -.5, 1., .8), '中生': (.5, -.3, 1., .8),
           '弱生': (.5, -.8, 1., .8)},
    '克': {'强克': (.7, -.5, -1., .8), '中克': (.5, -.6, -1., .8),
           '弱克': (.2, -.8, -1., .8)},
}


def calculate(actor_score, target_score, global_ratio, current_ratio,
              relation, actor_stem, target_stem, actor_root, target_root):
    """Return a scored operation, an explicit no-effect, or None for invalid inputs."""
    values = (actor_score, target_score, global_ratio, current_ratio)
    if (relation not in NORMAL or any(not isinstance(v, (int, float)) or
                                      not isfinite(v) or v <= 0 for v in values)):
        return None
    rooted = actor_root or target_root
    minimum = min(global_ratio, current_ratio)
    if relation == '生':
        if not actor_root and global_ratio <= .3 and current_ratio <= .3:
            level = '泄过为克'
            coefficient = max(-.5, min(-.1, -.1 - .3 * (.3 - minimum) / .3))
            actor_ratio, target_ratio, loss = -1., .8, 1.
        elif not target_root and global_ratio >= 3 and current_ratio >= 3:
            level = '虚不受生'
            coefficient = max(-.5, min(-.1, -.1 - .4 * (min(10., max(3., minimum)) - 3) / 7))
            actor_ratio, target_ratio, loss = -.5, -1., .5
        elif (rooted and global_ratio >= 1 and current_ratio >= 1.2) or (
                global_ratio >= 1.5 and current_ratio >= 1.8):
            level = '强生'
        elif (rooted and global_ratio >= .8 and current_ratio >= .8) or (
                global_ratio >= 1.2 and current_ratio >= 1.2):
            level = '中生'
        elif (global_ratio > .3 and current_ratio > .3) or (
                rooted and global_ratio > .1 and current_ratio > .1):
            level = '弱生'
        else:
            level = '不生'
    else:
        if global_ratio <= .2 and current_ratio < .2:
            level = '反克'
            coefficient = max(-.5, min(-.2, -.2 - .6 * (.6 - minimum)))
            actor_ratio, target_ratio, loss = -.8, .6, .8
        elif (rooted and global_ratio >= 1.5 and current_ratio >= 1) or (
                global_ratio >= 2 and current_ratio >= 1.5):
            level = '强克'
        elif (rooted and global_ratio < 2.5 and current_ratio >= .5) or (
                global_ratio < 2 and current_ratio >= .8):
            level = '中克'
        elif (rooted and global_ratio < 1.5 and current_ratio >= .1) or (
                global_ratio < 1.2 and current_ratio >= .2):
            level = '弱克'
        else:
            level = '不克'
    if level in ('不生', '不克'):
        return {'level': level, 'delta': 0., 'actor_change': 0.,
                'target_change': 0., 'polarity_coefficient': 0.}
    different = (actor_stem in YANG) != (target_stem in YANG)
    qualifies = different and global_ratio > .8 and current_ratio > .8
    polarity = (1. if qualifies else .8) if relation == '生' else (.6 if qualifies else 1.)
    if level in NORMAL[relation]:
        coefficient, actor_ratio, target_ratio, loss = NORMAL[relation][level]
    delta = min(actor_score, target_score) * abs(coefficient) * polarity
    return {'level': level, 'delta': delta,
            'actor_change': delta * actor_ratio * loss,
            'target_change': delta * target_ratio,
            'polarity_coefficient': polarity}
