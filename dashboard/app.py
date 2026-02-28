"""0DTE Command Centre — Flask dashboard.

Read-only dashboard for monitoring the iron condor bot.
Run: python dashboard/app.py
"""

import json
import os
import sys

# Ensure dashboard package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify

from data import (
    get_bot_status,
    get_cron_entries,
    get_market_session,
    get_open_positions,
    get_pdt_status,
    get_performance_metrics,
    get_recent_errors,
    get_spx_data,
    get_todays_closed_trades,
)
from config import STRATEGY_CONFIGS, TIME_EXIT, IC_WING_WIDTH

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        market=get_market_session(),
        spx=get_spx_data(),
        bot=get_bot_status(),
        positions=get_open_positions(),
        today=get_todays_closed_trades(),
        perf=get_performance_metrics("all"),
        strategies=STRATEGY_CONFIGS,
        time_exit=TIME_EXIT,
        ic_wing_width=IC_WING_WIDTH,
        system=_system_context(),
        pdt=get_pdt_status(),
    )


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@app.route("/partials/market")
def partial_market():
    return render_template(
        "partials/market_overview.html",
        market=get_market_session(),
        spx=get_spx_data(),
        bot=get_bot_status(),
    )


@app.route("/partials/positions")
def partial_positions():
    return render_template(
        "partials/open_positions.html",
        positions=get_open_positions(),
    )


@app.route("/partials/today")
def partial_today():
    return render_template(
        "partials/todays_trades.html",
        today=get_todays_closed_trades(),
    )


@app.route("/partials/performance")
def partial_performance():
    period = request.args.get("period", "all")
    return render_template(
        "partials/performance.html",
        perf=get_performance_metrics(period),
    )


@app.route("/partials/system")
def partial_system():
    return render_template(
        "partials/system_health.html",
        system=_system_context(),
    )


@app.route("/partials/pdt")
def partial_pdt():
    return render_template(
        "partials/pdt_tracker.html",
        pdt=get_pdt_status(),
    )


# ---------------------------------------------------------------------------
# JSON API for Chart.js
# ---------------------------------------------------------------------------

@app.route("/api/chart-data")
def api_chart_data():
    period = request.args.get("period", "all")
    perf = get_performance_metrics(period)
    return jsonify({
        "equity_curve": perf["equity_curve"],
        "calendar": perf["calendar"],
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _system_context() -> dict:
    return {
        "cron_entries": get_cron_entries(20),
        "errors": get_recent_errors(20),
        "bot": get_bot_status(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
