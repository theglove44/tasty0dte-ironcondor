"""Strategy configurations mirrored from main.py.

Kept separate to avoid importing bot modules (tastytrade SDK, env vars, etc).
Update here if STRATEGY_CONFIGS in main.py changes.
"""

STRATEGY_CONFIGS = [
    {
        'name': "20 Delta",
        'code': "IC-20D",
        'type': 'iron_condor',
        'target_delta': 0.20,
        'profit_target_pct': 0.25,
        'allowed_times': ["14:45", "15:30"],
    },
    {
        'name': "30 Delta",
        'code': "IC-30D",
        'type': 'iron_condor',
        'target_delta': 0.30,
        'profit_target_pct': 0.25,
        'allowed_times': [],
    },
    {
        'name': "Iron Fly V1",
        'code': "IF-V1",
        'type': 'iron_fly',
        'target_delta': 0.50,
        'profit_target_pct': 0.10,
        'wing_width': 10,
        'allowed_times': ["15:00"],
    },
    {
        'name': "Iron Fly V2",
        'code': "IF-V2",
        'type': 'iron_fly',
        'target_delta': 0.50,
        'profit_target_pct': 0.20,
        'wing_width': 10,
        'allowed_times': ["15:00"],
    },
    {
        'name': "Iron Fly V3",
        'code': "IF-V3",
        'type': 'iron_fly',
        'target_delta': 0.50,
        'profit_target_pct': 0.10,
        'wing_width': 10,
        'allowed_times': ["15:30"],
    },
    {
        'name': "Iron Fly V4",
        'code': "IF-V4",
        'type': 'iron_fly',
        'target_delta': 0.50,
        'profit_target_pct': 0.20,
        'wing_width': 10,
        'allowed_times': ["15:30"],
    },
    {
        'name': "Gap Filter 20D",
        'code': "GF-20D",
        'type': 'iron_condor',
        'target_delta': 0.20,
        'profit_target_pct': 0.25,
        'allowed_times': ["15:00", "15:30"],
        'overnight_filter': True,
    },
]

# Time exit rule (applies to iron flies)
TIME_EXIT = "18:00 UK"

# Wing width default for iron condors
IC_WING_WIDTH = 20
