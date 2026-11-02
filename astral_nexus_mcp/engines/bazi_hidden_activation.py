"""Map reviewed branch transfer records to legacy hidden-stem activation."""
from lunar_python.util import LunarUtil

from astral_nexus_mcp.engines.bazi_strength import RULES as WEIGHT_RULES

HE_KINDS = frozenset(('sanhui', 'sanhe', 'liuhe'))


def active_hidden(pillars, branch_replay):
    active = set()
    for pillar in pillars:
        for stem, qi in WEIGHT_RULES['branch_qi_type'][pillar['branch']].items():
            if qi == '本气':
                active.add((pillar['id'], stem))
    if branch_replay is None:
        return active
    if branch_replay.get('status') not in ('isolated_pair_stages', 'isolated_group_branch_stage'):
        raise ValueError('branch replay unavailable')
    for event in branch_replay['events']:
        if event['kind'] not in HE_KINDS:
            continue
        target = event.get('target_element')
        for change in event.get('changes', []):
            if (change['element'] == target and
                    LunarUtil.WU_XING_GAN[change['stem']] == target):
                active.add((change['pillar'], change['stem']))
    return active
