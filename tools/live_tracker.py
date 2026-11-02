#!/usr/bin/env python3
"""
Live trade tracker.
Upload a tastytrade fills screenshot → Claude vision extracts data → save to CSV.
Runs at http://localhost:5050

Usage:
    venv/bin/python tools/live_tracker.py
"""
from __future__ import annotations

import base64
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from project_paths import DATA_DIR, PAPER_TRADES_CSV  # noqa: E402

LIVE_CSV = DATA_DIR / "live_trades.csv"
BOT_CSV = PAPER_TRADES_CSV

LIVE_FIELDS = ["Date", "Entry_Time", "ATM", "Call_Wing", "Put_Wing",
               "Credit", "Exit_Time", "Exit_Debit", "Net_PL", "Notes"]

app = Flask(__name__)


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _init_csv() -> None:
    if not LIVE_CSV.exists():
        with open(LIVE_CSV, "w", newline="") as f:
            csv.writer(f).writerow(LIVE_FIELDS)


def load_live() -> list[dict]:
    _init_csv()
    with open(LIVE_CSV) as f:
        return list(csv.DictReader(f))


def save_trade(row: dict) -> None:
    _init_csv()
    # Overwrite if same date already exists, else append
    rows = load_live()
    existing = [r for r in rows if r["Date"] != row["Date"]]
    existing.append(row)
    existing.sort(key=lambda r: r["Date"])
    with open(LIVE_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LIVE_FIELDS)
        w.writeheader()
        w.writerows(existing)


def load_bot_v1() -> dict[str, dict]:
    """Load paper bot Iron Fly V1 trades keyed by date string."""
    out: dict[str, dict] = {}
    if not BOT_CSV.exists():
        return out
    with open(BOT_CSV) as f:
        for row in csv.DictReader(f):
            if row.get("Strategy") == "Iron Fly V1":
                out[row["Date"]] = row
    return out


# ── Claude vision extraction ──────────────────────────────────────────────────

EXTRACT_PROMPT = """You are parsing a tastytrade mobile app screenshot showing an Iron Fly or Iron Condor position.

Extract the following fields and return ONLY valid JSON (no markdown, no explanation):

{
  "entry_time": "HH:MM:SS" in 24h format (convert from AM/PM shown),
  "atm": integer strike where both short call and short put are placed,
  "call_wing": integer long call strike,
  "put_wing": integer long put strike,
  "credit": float credit collected (the "X.XX cr" value shown at entry),
  "exit_time": "HH:MM:SS" in 24h format or null if not shown,
  "exit_debit": float debit paid to close (the "X.XX db" value shown at closing) or null,
  "net_pl": float net P/L per share (e.g. -1.55) or null,
  "date_hint": "YYYY-MM-DD" if you can infer the date from expiry labels like "Jun 22", else null
}

Rules:
- The Iron Fly has 4 legs: short call, long call (higher strike), short put, long put (lower strike).
- ATM = the strike shared by the short call and short put.
- call_wing = long call strike (higher than ATM).
- put_wing = long put strike (lower than ATM).
- net_pl is the per-share P/L (small number like -1.55), NOT the dollar amount (-155.00).
- Times shown as e.g. "3:01:48p" → "15:01:48". "5:53:44p" → "17:53:44".
- If fields are not visible, use null.
"""


def extract_from_image(image_bytes: bytes, media_type: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    b64 = base64.standard_b64encode(image_bytes).decode()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }],
    )
    raw = msg.content[0].text.strip()
    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/extract", methods=["POST"])
def api_extract():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    f = request.files["image"]
    img_bytes = f.read()
    media_type = f.mimetype or "image/png"
    if media_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        media_type = "image/png"
    try:
        data = extract_from_image(img_bytes, media_type)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.json
    if not body:
        return jsonify({"error": "No data"}), 400
    row = {
        "Date":       body.get("date", str(date.today())),
        "Entry_Time": body.get("entry_time", ""),
        "ATM":        body.get("atm", ""),
        "Call_Wing":  body.get("call_wing", ""),
        "Put_Wing":   body.get("put_wing", ""),
        "Credit":     body.get("credit", ""),
        "Exit_Time":  body.get("exit_time", ""),
        "Exit_Debit": body.get("exit_debit", ""),
        "Net_PL":     body.get("net_pl", ""),
        "Notes":      body.get("notes", ""),
    }
    save_trade(row)
    return jsonify({"ok": True})


@app.route("/api/trades")
def api_trades():
    live = load_live()
    bot = load_bot_v1()
    rows = []
    for t in reversed(live):
        d = t["Date"]
        b = bot.get(d, {})
        rows.append({
            "date":          d,
            "live_credit":   t["Credit"],
            "live_debit":    t["Exit_Debit"],
            "live_pl":       t["Net_PL"],
            "live_atm":      t["ATM"],
            "live_call_wing": t["Call_Wing"],
            "live_put_wing": t["Put_Wing"],
            "live_entry":    t["Entry_Time"],
            "live_exit":     t["Exit_Time"],
            "live_notes":    t["Notes"],
            "bot_credit":    b.get("Credit Collected", ""),
            "bot_pl":        b.get("Exit P/L", ""),
            "bot_exit":      b.get("Exit Reason", b.get("Notes", "")[:40] if b.get("Notes") else ""),
            "bot_status":    b.get("Status", ""),
        })
    # Summary
    live_pls = [float(r["live_pl"]) for r in rows if r["live_pl"] not in ("", None)]
    bot_pls = [float(r["bot_pl"]) for r in rows if r["bot_pl"] not in ("", None)]
    summary = {
        "live_trades": len(live_pls),
        "live_total":  round(sum(live_pls), 2),
        "live_avg":    round(sum(live_pls) / len(live_pls), 3) if live_pls else 0,
        "live_wr":     round(100 * sum(1 for p in live_pls if p > 0) / len(live_pls), 1) if live_pls else 0,
        "bot_total":   round(sum(bot_pls), 2),
        "bot_avg":     round(sum(bot_pls) / len(bot_pls), 3) if bot_pls else 0,
        "bot_wr":      round(100 * sum(1 for p in bot_pls if p > 0) / len(bot_pls), 1) if bot_pls else 0,
    }
    return jsonify({"trades": rows, "summary": summary})


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Trade Tracker</title>
<style>
  :root {
    --bg: #0f1419; --surface: #1a2332; --border: #2a3f55;
    --text: #e0e6ed; --muted: #6b7f94; --green: #26a69a;
    --red: #ef5350; --amber: #ffa726; --blue: #42a5f5;
    --radius: 8px; --font: 'SF Mono', 'Fira Code', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 13px; }
  h1 { font-size: 18px; font-weight: 600; color: var(--blue); }
  h2 { font-size: 14px; font-weight: 600; color: var(--muted); letter-spacing: .05em; text-transform: uppercase; margin-bottom: 12px; }
  .header { padding: 20px 24px 16px; border-bottom: 1px solid var(--border); display:flex; align-items:center; gap:16px; }
  .tabs { display: flex; gap: 2px; padding: 0 24px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .tab { padding: 10px 20px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; transition: .15s; font-size: 12px; }
  .tab.active { color: var(--blue); border-bottom-color: var(--blue); }
  .panel { display: none; padding: 24px; max-width: 960px; }
  .panel.active { display: block; }

  /* Upload panel */
  .dropzone {
    border: 2px dashed var(--border); border-radius: var(--radius);
    padding: 48px 24px; text-align: center; cursor: pointer;
    transition: .2s; color: var(--muted);
  }
  .dropzone.over { border-color: var(--blue); background: rgba(66,165,245,.05); }
  .dropzone .icon { font-size: 40px; margin-bottom: 12px; }
  #preview-img { max-width: 100%; max-height: 320px; border-radius: var(--radius); margin-top: 16px; display: none; border: 1px solid var(--border); }
  .btn { padding: 9px 20px; border-radius: 6px; border: none; cursor: pointer; font-family: var(--font); font-size: 13px; font-weight: 600; }
  .btn-primary { background: var(--blue); color: #0f1419; }
  .btn-success { background: var(--green); color: #0f1419; }
  .btn-muted { background: var(--border); color: var(--text); }
  .btn:disabled { opacity: .4; cursor: default; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--blue); border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .status { margin-top: 12px; padding: 10px 14px; border-radius: 6px; font-size: 12px; }
  .status.ok { background: rgba(38,166,154,.15); color: var(--green); border: 1px solid rgba(38,166,154,.3); }
  .status.err { background: rgba(239,83,80,.15); color: var(--red); border: 1px solid rgba(239,83,80,.3); }

  /* Fields grid */
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px; }
  .field label { display: block; color: var(--muted); font-size: 11px; margin-bottom: 4px; }
  .field input, .field textarea {
    width: 100%; background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; padding: 8px 10px; color: var(--text);
    font-family: var(--font); font-size: 13px;
  }
  .field input:focus, .field textarea:focus { outline: none; border-color: var(--blue); }
  .field.full { grid-column: 1/-1; }
  .actions { margin-top: 16px; display: flex; gap: 10px; }

  /* Comparison table */
  .summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
  .stat-card .label { color: var(--muted); font-size: 11px; margin-bottom: 6px; }
  .stat-card .val { font-size: 22px; font-weight: 700; }
  .stat-card .sub { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .pos { color: var(--green); } .neg { color: var(--red); }

  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 10px; color: var(--muted); font-size: 11px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  td { padding: 8px 10px; border-bottom: 1px solid rgba(42,63,85,.5); font-size: 12px; }
  tr:hover td { background: rgba(66,165,245,.04); }
  .diff-pos { color: var(--green); } .diff-neg { color: var(--red); }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; }
  .badge.win { background: rgba(38,166,154,.2); color: var(--green); }
  .badge.loss { background: rgba(239,83,80,.2); color: var(--red); }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Live Trade Tracker</h1>
    <div style="color:var(--muted);font-size:11px;margin-top:3px">Iron Fly V1 — live vs paper bot</div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('upload')">Upload Trade</div>
  <div class="tab" onclick="showTab('log')">Trade Log</div>
</div>

<div id="tab-upload" class="panel active">
  <h2>Log a Trade</h2>
  <div class="dropzone" id="dz" onclick="document.getElementById('file-in').click()">
    <div class="icon">📸</div>
    <div>Drop your tastytrade screenshot here, or click to browse</div>
    <div style="font-size:11px;margin-top:6px">PNG or JPG of the entry + exit fills</div>
    <input type="file" id="file-in" accept="image/*" style="display:none">
    <img id="preview-img">
  </div>

  <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
    <button class="btn btn-primary" id="btn-extract" disabled onclick="doExtract()">Extract from image</button>
    <span id="extract-status"></span>
  </div>

  <div id="fields-section" style="display:none">
    <div class="fields">
      <div class="field">
        <label>Date</label>
        <input type="date" id="f-date">
      </div>
      <div class="field">
        <label>ATM Strike</label>
        <input type="number" id="f-atm">
      </div>
      <div class="field">
        <label>Long Call (wing strike)</label>
        <input type="number" id="f-call-wing">
      </div>
      <div class="field">
        <label>Long Put (wing strike)</label>
        <input type="number" id="f-put-wing">
      </div>
      <div class="field">
        <label>Entry Time</label>
        <input type="text" id="f-entry" placeholder="HH:MM:SS">
      </div>
      <div class="field">
        <label>Credit Collected ($)</label>
        <input type="number" step="0.01" id="f-credit">
      </div>
      <div class="field">
        <label>Exit Time</label>
        <input type="text" id="f-exit" placeholder="HH:MM:SS">
      </div>
      <div class="field">
        <label>Exit Debit ($)</label>
        <input type="number" step="0.01" id="f-debit">
      </div>
      <div class="field">
        <label>Net P/L per share ($)</label>
        <input type="number" step="0.01" id="f-pl">
      </div>
      <div class="field">
        <label>Notes</label>
        <input type="text" id="f-notes" placeholder="e.g. had to chase exit, filled 2c through mid">
      </div>
    </div>
    <div class="actions">
      <button class="btn btn-success" onclick="doSave()">Save trade</button>
      <button class="btn btn-muted" onclick="resetForm()">Reset</button>
      <span id="save-status"></span>
    </div>
  </div>
</div>

<div id="tab-log" class="panel">
  <div id="summary-section"></div>
  <h2>Day by day</h2>
  <div id="log-table">Loading…</div>
</div>

<script>
let currentFile = null;

// ── Drag & drop ───────────────────────────────────────────────────────────────
const dz = document.getElementById('dz');
const fileIn = document.getElementById('file-in');
const previewImg = document.getElementById('preview-img');

dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('over');
  if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
});
fileIn.addEventListener('change', () => { if (fileIn.files[0]) loadFile(fileIn.files[0]); });

function loadFile(f) {
  currentFile = f;
  const url = URL.createObjectURL(f);
  previewImg.src = url;
  previewImg.style.display = 'block';
  document.getElementById('btn-extract').disabled = false;
  // Pre-fill date from filename hint if present
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('f-date').value = today;
}

// ── Extract ────────────────────────────────────────────────────────────────────
async function doExtract() {
  const btn = document.getElementById('btn-extract');
  const status = document.getElementById('extract-status');
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> Extracting…';

  const fd = new FormData();
  fd.append('image', currentFile);
  try {
    const res = await fetch('/api/extract', { method: 'POST', body: fd });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    populateFields(json.data);
    document.getElementById('fields-section').style.display = 'block';
    status.innerHTML = '<span class="status ok">✓ Fields extracted — review and save</span>';
  } catch (e) {
    status.innerHTML = `<span class="status err">✗ ${e.message}</span>`;
  }
  btn.disabled = false;
}

function populateFields(d) {
  const today = new Date().toISOString().slice(0, 10);
  // Try to infer date from hint (e.g. "2026-06-22")
  let dt = d.date_hint || today;
  document.getElementById('f-date').value = dt;
  document.getElementById('f-atm').value = d.atm || '';
  document.getElementById('f-call-wing').value = d.call_wing || '';
  document.getElementById('f-put-wing').value = d.put_wing || '';
  document.getElementById('f-entry').value = d.entry_time || '';
  document.getElementById('f-credit').value = d.credit || '';
  document.getElementById('f-exit').value = d.exit_time || '';
  document.getElementById('f-debit').value = d.exit_debit || '';
  document.getElementById('f-pl').value = d.net_pl || '';
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function doSave() {
  const pl = parseFloat(document.getElementById('f-pl').value);
  const credit = parseFloat(document.getElementById('f-credit').value);
  const debit = parseFloat(document.getElementById('f-debit').value);
  // Auto-compute P/L if missing
  const netPl = isNaN(pl) && !isNaN(credit) && !isNaN(debit)
    ? Math.round((credit - debit) * 100) / 100
    : pl;

  const body = {
    date:       document.getElementById('f-date').value,
    entry_time: document.getElementById('f-entry').value,
    atm:        document.getElementById('f-atm').value,
    call_wing:  document.getElementById('f-call-wing').value,
    put_wing:   document.getElementById('f-put-wing').value,
    credit:     credit,
    exit_time:  document.getElementById('f-exit').value,
    exit_debit: debit,
    net_pl:     netPl,
    notes:      document.getElementById('f-notes').value,
  };

  const status = document.getElementById('save-status');
  try {
    const res = await fetch('/api/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error);
    status.innerHTML = '<span class="status ok">✓ Saved</span>';
    setTimeout(() => { showTab('log'); loadLog(); }, 800);
  } catch (e) {
    status.innerHTML = `<span class="status err">✗ ${e.message}</span>`;
  }
}

function resetForm() {
  ['f-date','f-atm','f-call-wing','f-put-wing','f-entry','f-credit','f-exit','f-debit','f-pl','f-notes']
    .forEach(id => document.getElementById(id).value = '');
  document.getElementById('fields-section').style.display = 'none';
  document.getElementById('extract-status').innerHTML = '';
  previewImg.style.display = 'none';
  currentFile = null;
  document.getElementById('btn-extract').disabled = true;
}

// ── Log ────────────────────────────────────────────────────────────────────────
async function loadLog() {
  const res = await fetch('/api/trades');
  const json = await res.json();
  renderSummary(json.summary);
  renderTable(json.trades);
}

function renderSummary(s) {
  const liveTotal = s.live_total;
  const botTotal = s.bot_total;
  const diff = Math.round((liveTotal - botTotal) * 100) / 100;
  document.getElementById('summary-section').innerHTML = `
    <div class="summary-grid" style="margin-bottom:24px">
      <div class="stat-card">
        <div class="label">YOUR LIVE TRADES</div>
        <div class="val ${liveTotal >= 0 ? 'pos' : 'neg'}">${liveTotal >= 0 ? '+' : ''}$${liveTotal.toFixed(2)}</div>
        <div class="sub">${s.live_trades} trades · ${s.live_wr}% WR · avg ${s.live_avg >= 0 ? '+' : ''}$${s.live_avg.toFixed(3)}</div>
      </div>
      <div class="stat-card">
        <div class="label">BOT (same days)</div>
        <div class="val ${botTotal >= 0 ? 'pos' : 'neg'}">${botTotal >= 0 ? '+' : ''}$${botTotal.toFixed(2)}</div>
        <div class="sub">${s.live_trades} days · ${s.bot_wr}% WR · avg ${s.bot_avg >= 0 ? '+' : ''}$${s.bot_avg.toFixed(3)}</div>
      </div>
    </div>
    <div style="margin-bottom:20px;font-size:12px;color:var(--muted)">
      Execution delta vs bot: <span class="${diff >= 0 ? 'pos' : 'neg'}" style="font-weight:700">${diff >= 0 ? '+' : ''}$${diff.toFixed(2)}</span>
      across ${s.live_trades} matched days
    </div>
  `;
}

function renderTable(trades) {
  if (!trades.length) {
    document.getElementById('log-table').innerHTML = '<div style="color:var(--muted);padding:20px 0">No trades logged yet.</div>';
    return;
  }
  const rows = trades.map(t => {
    const lpl = parseFloat(t.live_pl);
    const bpl = parseFloat(t.bot_pl);
    const diff = !isNaN(lpl) && !isNaN(bpl) ? Math.round((lpl - bpl) * 100) / 100 : null;
    const lWin = !isNaN(lpl) && lpl > 0;
    const bWin = !isNaN(bpl) && bpl > 0;
    const lcr = parseFloat(t.live_credit);
    const bcr = parseFloat(t.bot_credit);
    const crDiff = !isNaN(lcr) && !isNaN(bcr) ? Math.round((lcr - bcr) * 100) / 100 : null;

    return `<tr>
      <td style="color:var(--muted)">${t.date}</td>
      <td>${t.live_atm || '—'}</td>
      <td>${!isNaN(lcr) ? '$' + lcr.toFixed(2) : '—'}</td>
      <td>${!isNaN(bcr) ? '$' + bcr.toFixed(2) : '—'}</td>
      <td class="${crDiff !== null ? (crDiff >= 0 ? 'diff-pos' : 'diff-neg') : ''}">${crDiff !== null ? (crDiff >= 0 ? '+' : '') + '$' + crDiff.toFixed(2) : '—'}</td>
      <td><span class="badge ${lWin ? 'win' : 'loss'}">${!isNaN(lpl) ? (lpl >= 0 ? '+' : '') + '$' + lpl.toFixed(2) : '—'}</span></td>
      <td><span class="badge ${bWin ? 'win' : 'loss'}">${!isNaN(bpl) ? (bpl >= 0 ? '+' : '') + '$' + bpl.toFixed(2) : '—'}</span></td>
      <td class="${diff !== null ? (diff >= 0 ? 'diff-pos' : 'diff-neg') : ''}">${diff !== null ? (diff >= 0 ? '+' : '') + '$' + diff.toFixed(2) : '—'}</td>
      <td style="color:var(--muted);font-size:11px">${t.live_notes || ''}</td>
    </tr>`;
  }).join('');

  document.getElementById('log-table').innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date</th><th>ATM</th>
          <th>Live Credit</th><th>Bot Credit</th><th>Cr Δ</th>
          <th>Live P/L</th><th>Bot P/L</th><th>P/L Δ</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['upload','log'][i] === name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'log') loadLog();
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    _init_csv()
    port = int(os.environ.get("TRACKER_PORT", 5050))
    print(f"\n  Live Trade Tracker → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
