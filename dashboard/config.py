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
        # In main.py this strategy has no allowed_times override,
        # so it runs at all scheduler trigger times.
        'allowed_times': ["14:45", "15:00", "15:30"],
        'profit_target_pct': 0.25,
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
    {
        'name': "Dynamic 0DTE",
        'code': "DY-0D",
        'type': 'dynamic_0dte',
        'target_delta': "adaptive",
        'profit_target_pct': 0.20,
        'allowed_times': ["15:00"],
        'move_threshold': -0.1,
        'condor_delta': 0.20,
        'condor_wing_width': 20,
        'fly_delta': 0.50,
        'fly_wing_width': 10,
    },
    {
        'name': "Premium Popper",
        'code': "PP-ORB",
        'type': 'premium_popper',
        'target_delta': 0.20,
        'profit_target_pct': 0.50,
        'allowed_times': ["14:45"],
    },
]

# Time exit rules from monitor.py
TIME_EXIT = "18:00 UK (30 Delta + Iron Fly), 19:50 UK (Premium Popper), 20:55 UK (Dynamic 0DTE)"

# Wing width default for iron condors
IC_WING_WIDTH = 20
