# Trade Analysis Scripts

Reusable scripts for analysing `paper_trades.csv` and regenerating the public site at `public_site/`. All scripts share a common library (`common.py`) for filters, DST normalisation, and stat helpers.

## Quick reference

| Script | What it does | Run after |
|---|---|---|
| `regenerate_site_data.py` | Rebuilds `public_site/data.js` from the CSV | Any CSV change |
| `dedup_trades.py` | Finds & removes duplicate trade rows | Suspected double-logging from the bot |
| `strategy_metrics.py` | Deep performance metrics for one strategy/bucket | Ad-hoc analysis |
| `exit_analysis.py` | Exit-reason breakdown (profit-target / time-stop / settled) | Reviewing exit logic |

## Setup

These scripts require `pandas` and `numpy`. If you don't have them already:

```bash
pip install pandas numpy
```

All scripts use absolute paths relative to the project root, so you can run them from anywhere. Examples below assume you're in the project root.

## Common filters (applied by default in every script)

- **Closed-only**: rows where `Status` is `CLOSED` or `EXPIRED` and `Exit P/L` is present. Drops `OPEN` positions.
- **Private strategies excluded**: `Premium Popper`, `ORB-STACK-*`, `JadeLizard_*`. These are custom strategies kept out of the public analysis. Override with `--include-private`.
- **Outlier filter**: trades with `Credit Collected > $30` are dropped (the known cases are 5 trades on 2026-03-20 with anomalous credits 7-8× normal). Override with `--keep-outliers`.

All three filters are defined in `analysis/common.py` if you need to adjust them.

## Scripts

### `regenerate_site_data.py`

Rebuilds `public_site/data.js`. Run after the CSV changes for any reason — new trades, manual edits, dedup, outlier review.

```bash
python3 analysis/regenerate_site_data.py
python3 analysis/regenerate_site_data.py --csv /path/to/other.csv --out /tmp/data.js
```

Output is a single JS file containing `window.SITE_DATA` with: meta, overall stats, per-strategy stats, per-bucket breakdown, monthly P/L, daily equity curve, deep metrics for the top 5 profitable strategies, and a day-of-week × month grid for V1 and Dynamic 0DTE.

### `dedup_trades.py`

Finds duplicate rows in the CSV (same Date + Strategy + Entry Time, or same strategy/strikes within 60 seconds). Report only by default; pass `--apply` to actually remove duplicates.

```bash
python3 analysis/dedup_trades.py            # report only
python3 analysis/dedup_trades.py --apply    # remove & backup
python3 analysis/dedup_trades.py --apply --no-backup
```

A timestamped backup file is created next to the CSV unless `--no-backup` is passed.

### `strategy_metrics.py`

Deep metrics for a single (strategy, bucket) combination. Prints:
- Win rate, totals, expectancy
- Win/loss streaks
- Drawdowns (max, episodes, median, length)
- Risk-adjusted ratios (Sharpe, Sortino, Calmar)
- Skewness, kurtosis
- IV regime breakdown
- SPX day-move breakdown
- Time-of-exit clustering
- Sequential autocorrelation
- Hold time stats

```bash
python3 analysis/strategy_metrics.py "Iron Fly V1" --bucket 30
python3 analysis/strategy_metrics.py "Dynamic 0DTE" --bucket 30
python3 analysis/strategy_metrics.py "Iron Fly V3" --bucket 60
python3 analysis/strategy_metrics.py "20 Delta"   # all buckets pooled
```

### `exit_analysis.py`

Breaks down trades by exit reason (profit-target / time-stop / settled) and dives into each category, including DOW and month split for time-stops specifically.

```bash
python3 analysis/exit_analysis.py "Iron Fly V1"
python3 analysis/exit_analysis.py "Iron Fly V1" --bucket 30
python3 analysis/exit_analysis.py --all   # one-line summary per strategy
```

## Typical workflows

### Weekly update after the bot has been trading

```bash
python3 analysis/dedup_trades.py                  # check for Discord double-fires
python3 analysis/dedup_trades.py --apply          # if duplicates were found
python3 analysis/regenerate_site_data.py          # update data.js
# Then drag public_site/ to Cloudflare Pages
```

### Investigating a strategy's exit behaviour

```bash
python3 analysis/exit_analysis.py "Iron Fly V1" --bucket 30
python3 analysis/strategy_metrics.py "Iron Fly V1" --bucket 30
```

### Comparing two strategies

```bash
python3 analysis/strategy_metrics.py "Iron Fly V1" --bucket 30 > /tmp/v1.txt
python3 analysis/strategy_metrics.py "Iron Fly V2" --bucket 30 > /tmp/v2.txt
diff /tmp/v1.txt /tmp/v2.txt
```

### Including private strategies for personal analysis

```bash
python3 analysis/strategy_metrics.py "Premium Popper" --bucket 30 --include-private
```

## Adding new scripts

All shared logic lives in `common.py`:
- `load_trades(csv_path, ...)` — load and prep the CSV with standard filters
- `streaks()`, `drawdown_episodes()` — stat helpers
- `iv_bin()`, `move_bin()`, `exit_window_bin()` — categorisation
- `classify_exit()`, `hold_minutes()` — per-row helpers
- `bucket_label()` — format minutes-after-open as `+30m`, `+1h00m`, etc.
- `is_private_strategy()` — single source of truth for private/public split

Import from `common` rather than re-implementing. Path resolution from the analysis directory:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
```
