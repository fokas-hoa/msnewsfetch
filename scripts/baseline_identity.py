"""Explicit baseline card identity migration. No fuzzy clinical-trial joins.

Programme-level announcements intentionally have no trial ID: the existing phase-1
trial must not overwrite an announced phase-2 programme's development status.
"""
from research_contract import record_ids

IDS = {
    'CCMR Two': ('ccmr-two', ['NCT05131828']),
    'OCTOPUS': ('octopus-metformin', []),
    'MACSiMiSE-BRAIN': ('macsimise-brain', ['NCT05893225']),
    'Metformin in aging MS': ('metformin-aging-ms', ['NCT06463743']),
    'MODIF-MS': ('modif-ms', ['2023-507874-42-00', 'NCT06330077']),
    'ReCOVER': ('recover', ['NCT02521311']),
    'ReVIVE': ('revive', ['NCT05359653']),
    'ReINFORCE': ('reinforce', ['NCT06065670']),
    'ACT-1004-1239': ('act-1004-1239', ['2025-522922-11-00']),
    'PIPE-307 / VISTA': ('pipe-307', ['NCT06083753']),
    'SetPoint MS Pilot': ('setpoint-ms', ['NCT06796504']),
    'TOTEM-RRMS': ('totem-rrms', ['NCT03910738']),
    'PTD802': ('ptd802', []),
    'Lucid-MS / Lucid-21-302': ('lucid-ms', []),
}


def migrate(data):
    for section in ('pipeline', 'translational', 'readouts'):
        for item in data.get(section, []):
            cid, identifiers = IDS.get(item.get('name'), (None, record_ids(item.get('url'))))
            item['record_ids'] = identifiers
            if cid:
                item['canonical_id'] = cid
            item['baseline_date'] = data.get('siteUpdated')
            if section == 'readouts':
                item['readout_summary'] = item.get('status', '')
    for index, item in enumerate(data.get('greece', [])):
        item['record_ids'] = record_ids(' '.join(x.get('url', '') for x in item.get('sources', [])))
        # These two curated cards made snapshot-specific access claims. They must
        # not sit above a live feed as assertions of CURRENT access.
        if index in (0, 1):
            item['historical_access_snapshot'] = True
    return data
