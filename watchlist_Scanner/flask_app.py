"""
ASX/US Stock Data Manager - PythonAnywhere Web App
===================================================
Dashboard for managing stock data + Channel Finder Scanner + Charts.

PythonAnywhere WSGI setup:
  import sys
  sys.path.insert(0, '/home/JimmyTrader/watchlist_Scanner')
  from flask_app import app as application
"""

import os
import sys
import threading
import subprocess
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Find the real Python executable (sys.executable is uwsgi inside the web app)
PYTHON = os.path.join(sys.prefix, 'bin', 'python3')
if not os.path.exists(PYTHON):
    PYTHON = os.path.join(sys.prefix, 'bin', 'python')

from flask import Flask, redirect, jsonify, request, Response, send_from_directory
import pymysql

from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT, ADMIN_PASSWORD, SECRET_KEY
from db_channel_scanner import run_scan, load_last_results, get_connection, get_ticker_data
from db_picks import (init_tables, get_account, get_positions, get_portfolio_value,
                      get_history, buy_stock, sell_stock, UPLOADS_DIR)
from db_ask import (init_tables as init_ask_tables, register_user, login_user,
                    submit_question, answer_question, get_questions, get_username)

from flask import session

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload


def is_admin():
    return session.get('admin') is True

# Init tables on startup
try:
    init_tables()
    init_ask_tables()
except Exception:
    pass


def fmt_num(val):
    """Format number removing unnecessary trailing zeros."""
    if val == int(val):
        return f"{int(val):,}"
    s = f"{val:,.4f}".rstrip('0')
    return s if not s.endswith('.') else s + '0'


def current_user_id():
    return session.get('user_id')

def current_username():
    return session.get('username', '')

LOG_FILE = os.path.join(BASE_DIR, 'last_run.log')
_job_lock   = threading.Lock()
_job_running = False
_job_name    = ''


# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_db_stats():
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT ticker) FROM prices")
            tickers = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM prices")
            rows = cur.fetchone()[0]
            cur.execute("SELECT MAX(date) FROM prices")
            latest = cur.fetchone()[0]
            cur.execute("SELECT MIN(date) FROM prices")
            earliest = cur.fetchone()[0]
        conn.close()
        return {
            'tickers': tickers,
            'rows': f"{rows:,}",
            'latest': str(latest) if latest else 'N/A',
            'earliest': str(earliest) if earliest else 'N/A',
            'error': None,
        }
    except Exception as e:
        return {'tickers': 0, 'rows': 0, 'latest': 'N/A', 'earliest': 'N/A', 'error': str(e)}


def get_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            return f.read()
    return 'No log yet.'


# ─── Background job ───────────────────────────────────────────────────────────

def _run_script(script_path, label):
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== {label} ===\nStarted: {datetime.now()}\n\n")
    try:
        proc = subprocess.Popen(
            [PYTHON, '-u', script_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=BASE_DIR
        )
        with open(LOG_FILE, 'a') as f:
            for line in proc.stdout:
                f.write(line)
                f.flush()
        proc.wait()
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nFinished: {datetime.now()}\nExit code: {proc.returncode}\n")
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nERROR: {e}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name = ''


def _run_scan_job():
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Channel Finder Scan ===\nStarted: {datetime.now()}\n\n")

    def log_to_file(msg):
        with open(LOG_FILE, 'a') as f:
            f.write(msg)
            f.flush()

    try:
        run_scan(log_callback=log_to_file)
    except Exception as e:
        log_to_file(f"\nERROR: {e}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name = ''


def start_script_job(script_path, label):
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name = label
    t = threading.Thread(target=_run_script, args=(script_path, label), daemon=True)
    t.start()
    return True


def start_scan_job():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name = 'Channel Scan'
    t = threading.Thread(target=_run_scan_job, daemon=True)
    t.start()
    return True


# ─── Shared CSS + nav ─────────────────────────────────────────────────────────

BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f1117; color: #e0e0e0; min-height: 100vh; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: #1a1d2e; border-bottom: 1px solid #2a2d3e;
         padding: 14px 28px; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
header h1 { font-size: 1.1rem; font-weight: 700; color: #fff; }
nav { display: flex; gap: 6px; }
nav a { padding: 6px 14px; border-radius: 6px; font-size: 0.82rem; font-weight: 500;
        color: #aaa; background: #252839; }
nav a:hover, nav a.active { background: #3b82f6; color: #fff; text-decoration: none; }
.badge { font-size: 0.72rem; padding: 3px 10px; border-radius: 20px;
         font-weight: 600; color: #fff; margin-left: auto; }
main { padding: 28px; max-width: 1200px; margin: 0 auto; }
.card { background: #1a1d2e; border: 1px solid #2a2d3e; border-radius: 8px; padding: 20px; }
.grid4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 14px; margin-bottom: 24px; }
.stat-label { font-size: 0.72rem; color: #666; text-transform: uppercase; letter-spacing:.05em; margin-bottom: 5px; }
.stat-value { font-size: 1.7rem; font-weight: 700; color: #fff; }
.stat-sub   { font-size: 0.78rem; color: #555; margin-top: 3px; }
section { background: #1a1d2e; border: 1px solid #2a2d3e; border-radius: 8px;
          padding: 22px; margin-bottom: 20px; }
h2 { font-size: 0.82rem; font-weight: 600; color: #777; text-transform: uppercase;
     letter-spacing:.06em; margin-bottom: 16px; }
.btn { display: inline-block; padding: 9px 18px; border-radius: 6px; font-size: 0.88rem;
       font-weight: 600; cursor: pointer; border: none; text-decoration: none; transition: opacity .15s; }
.btn:hover { opacity: .82; text-decoration: none; }
.btn-blue   { background: #3b82f6; color: #fff; }
.btn-amber  { background: #f59e0b; color: #000; }
.btn-green  { background: #22c55e; color: #000; }
.btn-off    { background: #252839; color: #555; cursor: not-allowed; }
.btn-row    { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.note       { font-size: 0.78rem; color: #555; margin-top: 10px; }
pre { background: #0a0c14; border: 1px solid #2a2d3e; border-radius: 6px; padding: 14px;
      font-size: 0.78rem; line-height: 1.5; max-height: 460px; overflow-y: auto;
      white-space: pre-wrap; word-break: break-word; color: #86efac; font-family: monospace; }
.err-box { background: #2a1515; border: 1px solid #ef4444; border-radius: 8px;
           padding: 14px; margin-bottom: 20px; color: #f87171; font-size:.85rem; }
"""

def nav_html(active=''):
    with _job_lock:
        running = _job_running
        jname = _job_name
    badge = f'<span class="badge" style="background:#f59e0b">⚙ {jname}</span>' if running else \
            '<span class="badge" style="background:#22c55e">● Idle</span>'
    def lnk(href, label, key):
        cls = 'active' if active == key else ''
        return f'<a href="{href}" class="{cls}">{label}</a>'
    if is_admin():
        auth_btn = '<a href="/logout" style="font-size:.78rem;color:#555;margin-left:8px">Admin Logout</a>'
    elif current_user_id():
        auth_btn = f'<span style="font-size:.78rem;color:#aaa;margin-left:8px">Hi, {current_username()}</span> <a href="/ask/logout" style="font-size:.78rem;color:#555;margin-left:6px">Logout</a>'
    else:
        auth_btn = '<a href="/ask/login" style="font-size:.78rem;padding:5px 12px;background:#252839;border-radius:6px;color:#aaa">Login</a>'
    return f"""
    <header>
      <h1>Stock Manager</h1>
      <nav>
        {lnk('/','Dashboard','home')}
        {lnk('/scan','Channel Scanner','scan')}
        {lnk('/results','Results','results')}
        {lnk('/picks',"Jimmy's Picks",'picks')}
        {lnk('/ask','Ask Jimmy','ask')}
        {lnk('/log-view','Log','log')}
      </nav>
      {badge}
      {auth_btn}
    </header>"""


def page_wrap(title, active, content, auto_refresh=False):
    refresh = '<meta http-equiv="refresh" content="5">' if auto_refresh else ''
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Stock Manager</title>
{refresh}
<style>{BASE_CSS}</style>
</head>
<body>
{nav_html(active)}
<main>{content}</main>
</body>
</html>"""


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    stats     = get_db_stats()
    positions = get_positions()
    history   = get_history()
    cash      = get_account()
    port_val  = get_portfolio_value(positions)
    total_val = cash + port_val
    total_pnl = total_val - 100_000.0

    # Win rate from closed trades
    closed = [t for t in history if t['pnl'] is not None]
    wins   = [t for t in closed if t['pnl'] > 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0
    total_realised = sum(t['pnl'] for t in closed)

    with _job_lock:
        running = _job_running

    err = f'<div class="err-box"><strong>DB Error:</strong> {stats["error"]}</div>' if stats['error'] else ''

    if not is_admin():
        daily_btn = initial_btn = ''
    elif running:
        daily_btn   = '<span class="btn btn-off">Run Daily Update</span>'
        initial_btn = '<span class="btn btn-off">Run Initial Download</span>'
    else:
        daily_btn   = '<a href="/run-daily" class="btn btn-blue">Run Daily Update</a>'
        initial_btn = '<a href="/run-initial" class="btn btn-amber" onclick="return confirm(\'This takes 1–2 hours. Continue?\')">Run Initial Download</a>'

    pnl_color = '#22c55e' if total_pnl >= 0 else '#ef4444'
    pnl_sign  = '+' if total_pnl >= 0 else ''
    wr_color  = '#22c55e' if win_rate >= 50 else '#ef4444'
    rp_color  = '#22c55e' if total_realised >= 0 else '#ef4444'
    rp_sign   = '+' if total_realised >= 0 else ''

    # Recent trade history rows
    hist_rows = ''
    for t in history[:10]:
        action_color = '#22c55e' if t['action'] == 'BUY' else '#ef4444'
        pnl_str = ''
        if t['pnl'] is not None:
            pc = '#22c55e' if t['pnl'] >= 0 else '#ef4444'
            ps = '+' if t['pnl'] >= 0 else ''
            pnl_str = f'<span style="color:{pc}">{ps}${t["pnl"]:,.2f}</span>'
        hist_rows += f"""<tr>
          <td>{t['trade_date']}</td>
          <td><a href="/chart/{t['ticker']}" style="color:#60a5fa;font-weight:700">{t['ticker']}</a></td>
          <td><span style="color:{action_color};font-weight:700">{t['action']}</span></td>
          <td>{fmt_num(t['shares'])}</td>
          <td>${fmt_num(t['price'])}</td>
          <td>${t['total']:,.2f}</td>
          <td>{pnl_str}</td>
        </tr>"""

    content = f"""
    {err}

    <!-- Portfolio Hero -->
    <div style="background:linear-gradient(135deg,#1a1d2e 0%,#0f1117 100%);border:1px solid #2a2d3e;
                border-radius:12px;padding:28px;margin-bottom:24px">
      <div style="font-size:.78rem;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Jimmy's Portfolio — Starting Balance $100,000</div>
      <div style="font-size:2.8rem;font-weight:800;color:#fff;margin-bottom:4px">${total_val:,.2f}</div>
      <div style="font-size:1.1rem;font-weight:700;color:{pnl_color}">{pnl_sign}${total_pnl:,.2f} &nbsp;
        <span style="font-size:.85rem;font-weight:500">({pnl_sign}{total_pnl/1000:.2f}% on $100k)</span>
      </div>
    </div>

    <!-- Stats row -->
    <div class="grid4" style="margin-bottom:24px">
      <div class="card">
        <div class="stat-label">Cash Available</div>
        <div class="stat-value" style="font-size:1.4rem">${cash:,.2f}</div>
        <div class="stat-sub">ready to deploy</div>
      </div>
      <div class="card">
        <div class="stat-label">Open Positions</div>
        <div class="stat-value" style="font-size:1.4rem">{len(positions)}</div>
        <div class="stat-sub">portfolio value ${port_val:,.2f}</div>
      </div>
      <div class="card">
        <div class="stat-label">Win Rate</div>
        <div class="stat-value" style="font-size:1.4rem;color:{wr_color}">{win_rate:.0f}%</div>
        <div class="stat-sub">{len(wins)} wins from {len(closed)} closed trades</div>
      </div>
      <div class="card">
        <div class="stat-label">Realised P&amp;L</div>
        <div class="stat-value" style="font-size:1.4rem;color:{rp_color}">{rp_sign}${total_realised:,.2f}</div>
        <div class="stat-sub">from closed trades</div>
      </div>
    </div>

    <!-- Recent trades -->
    <section style="margin-bottom:24px">
      <h2>Recent Trades <a href="/picks" style="font-size:.75rem;font-weight:400;color:#3b82f6;text-transform:none;margin-left:10px;letter-spacing:0">View full portfolio →</a></h2>
      <style>
        .trade-table{{width:100%;border-collapse:collapse;font-size:.83rem}}
        .trade-table th{{text-align:left;padding:8px 10px;color:#555;border-bottom:1px solid #2a2d3e;font-weight:500}}
        .trade-table td{{padding:8px 10px;border-bottom:1px solid #151820}}
        .trade-table tr:hover td{{background:#1f2235}}
      </style>
      {'<table class="trade-table"><tr><th>Date</th><th>Ticker</th><th>Action</th><th>Shares</th><th>Price</th><th>Total</th><th>P&L</th></tr>' + hist_rows + '</table>' if hist_rows else '<p class="note">No trades yet. <a href="/picks">Add your first pick →</a></p>'}
    </section>

    <!-- Admin data actions -->
    {'<section><h2>Data Actions</h2><div class="btn-row">' + daily_btn + initial_btn + '</div><p class="note">Daily update fetches only new rows.</p></section>' if is_admin() else ''}
    """

    return page_wrap('Dashboard', 'home', content, auto_refresh=running)


# ─── Channel Scanner ──────────────────────────────────────────────────────────

@app.route('/scan')
def scan_page():
    with _job_lock:
        running = _job_running
        jname = _job_name

    last = load_last_results()
    last_info = ''
    if last:
        last_info = f'<p class="note">Last scan: {last["scan_date"]} — {last["total"]} setups found ({last["both"]} BOTH, {last["single"]} SINGLE). <a href="/results">View results →</a></p>'

    if not is_admin():
        btn = ''
    elif running and jname == 'Channel Scan':
        btn = '<span class="btn btn-off">Scan Running...</span>'
    elif running:
        btn = '<span class="btn btn-off">Another job running</span>'
    else:
        btn = '<a href="/run-scan" class="btn btn-green">▶ Run Channel Scanner</a>'

    log_section = ''
    if running and jname == 'Channel Scan':
        log_section = f'<section><h2>Live Log</h2><pre>{get_log().replace("<","&lt;")}</pre></section>'

    content = f"""
    <section>
      <h2>Channel Finder Scanner</h2>
      <p style="color:#aaa;margin-bottom:16px;font-size:.9rem">
        Scans all {{}}) tickers for EMA squeeze channels on Daily + Weekly timeframes.<br>
        <strong style="color:#fff">BOTH (2/2)</strong> = daily + weekly channel aligned.
        <strong style="color:#fff">SINGLE (1/2)</strong> = one timeframe only.
      </p>
      <div class="btn-row">{btn}</div>
      {last_info}
    </section>
    {log_section}"""

    return page_wrap('Channel Scanner', 'scan', content, auto_refresh=(running and jname == 'Channel Scan'))


@app.route('/run-scan')
def run_scan_route():
    if not is_admin():
        return redirect('/scan')
    start_scan_job()
    return redirect('/scan')


# ─── Results ─────────────────────────────────────────────────────────────────

@app.route('/results')
def results_page():
    data = load_last_results()

    if not data:
        content = '<section><h2>No Results Yet</h2><p class="note">Run the Channel Scanner first.</p><br><a href="/scan" class="btn btn-green">Go to Scanner</a></section>'
        return page_wrap('Results', 'results', content)

    results = data['results']
    both_rows   = [r for r in results if r['score'] == 2]
    single_rows = [r for r in results if r['score'] == 1]

    def rows_html(items):
        html = ''
        for r in items:
            w = '✓' if r['weekly'] else '–'
            d = '✓' if r['daily']  else '–'
            score_color = '#22c55e' if r['score'] == 2 else '#f59e0b'
            html += f"""
            <tr onclick="window.location='/chart/{r['ticker']}'" style="cursor:pointer">
              <td><strong style="color:#60a5fa">{r['ticker']}</strong></td>
              <td data-val="{r['price']}">${r['price']:,.4f}</td>
              <td data-val="{r['score']}"><span style="color:{score_color};font-weight:700">{r['score']}/2</span></td>
              <td style="color:{'#22c55e' if r['weekly'] else '#555'}">{w}</td>
              <td style="color:{'#22c55e' if r['daily'] else '#555'}">{d}</td>
              <td><a href="/chart/{r['ticker']}" class="btn btn-blue" style="padding:4px 10px;font-size:.78rem" onclick="event.stopPropagation()">Chart</a></td>
            </tr>"""
        return html

    table_style = """
    <style>
    table { width:100%; border-collapse:collapse; font-size:.85rem; }
    th { text-align:left; padding:8px 12px; color:#555; border-bottom:1px solid #2a2d3e;
         font-weight:500; cursor:pointer; user-select:none; white-space:nowrap; }
    th:hover { color:#aaa; }
    th.sort-asc::after  { content:' ▲'; font-size:.65rem; color:#60a5fa; }
    th.sort-desc::after { content:' ▼'; font-size:.65rem; color:#60a5fa; }
    td { padding:9px 12px; border-bottom:1px solid #151820; }
    tr:hover td { background:#1f2235; }
    </style>
    <script>
    function sortTable(th) {
      const table = th.closest('table');
      const tbody = table.querySelector('tbody');
      const idx = th.cellIndex;
      const asc = th.classList.contains('sort-desc');
      table.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const av = a.cells[idx].dataset.val ?? a.cells[idx].textContent.trim();
        const bv = b.cells[idx].dataset.val ?? b.cells[idx].textContent.trim();
        const an = parseFloat(av), bn = parseFloat(bv);
        const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
        return asc ? cmp : -cmp;
      });
      rows.forEach(r => tbody.appendChild(r));
    }
    </script>"""

    both_section = ''
    if both_rows:
        both_section = f"""
        <section>
          <h2>BOTH — Daily + Weekly Channel ({len(both_rows)} stocks)</h2>
          {table_style}
          <table>
            <thead><tr>
              <th onclick="sortTable(this)">Ticker</th>
              <th onclick="sortTable(this)" class="sort-desc">Price</th>
              <th onclick="sortTable(this)">Score</th>
              <th>Weekly</th><th>Daily</th><th></th>
            </tr></thead>
            <tbody>{rows_html(both_rows)}</tbody>
          </table>
        </section>"""

    single_section = ''
    if single_rows:
        single_section = f"""
        <section>
          <h2>SINGLE — One Timeframe ({len(single_rows)} stocks)</h2>
          {table_style}
          <table>
            <thead><tr>
              <th onclick="sortTable(this)">Ticker</th>
              <th onclick="sortTable(this)" class="sort-desc">Price</th>
              <th onclick="sortTable(this)">Score</th>
              <th>Weekly</th><th>Daily</th><th></th>
            </tr></thead>
            <tbody>{rows_html(single_rows)}</tbody>
          </table>
        </section>"""

    summary = f"""
    <section style="padding:16px 22px;margin-bottom:20px">
      <div style="display:flex;gap:32px;align-items:center;flex-wrap:wrap">
        <div><span style="color:#555;font-size:.8rem">Scan date:</span>
             <strong style="margin-left:8px">{data['scan_date']}</strong></div>
        <div><span style="color:#555;font-size:.8rem">Total:</span>
             <strong style="margin-left:8px">{data['total']}</strong></div>
        <div><span style="color:#22c55e;font-size:.8rem">BOTH:</span>
             <strong style="margin-left:8px;color:#22c55e">{data['both']}</strong></div>
        <div><span style="color:#f59e0b;font-size:.8rem">SINGLE:</span>
             <strong style="margin-left:8px;color:#f59e0b">{data['single']}</strong></div>
        <a href="/run-scan" class="btn btn-green" style="margin-left:auto;padding:7px 16px;font-size:.82rem">Re-run Scan</a>
      </div>
    </section>"""

    content = summary + both_section + single_section
    return page_wrap('Results', 'results', content)


# ─── Chart ────────────────────────────────────────────────────────────────────

@app.route('/chart/<ticker>')
def chart_page(ticker):
    ticker = ticker.upper()
    content = f"""
    <div style="margin-bottom:16px;display:flex;align-items:center;gap:16px">
      <a href="/results" style="color:#555;font-size:.85rem">← Back to Results</a>
      <h1 style="font-size:1.4rem;font-weight:700;color:#fff">{ticker}</h1>
    </div>

    <section style="padding:16px">
      <div id="chart" style="width:100%;height:520px;background:#0a0c14;border-radius:6px"></div>
      <div id="volume-chart" style="width:100%;height:120px;background:#0a0c14;border-radius:6px;margin-top:4px"></div>
      <div id="status" style="color:#555;font-size:.8rem;margin-top:8px">Loading chart data...</div>
    </section>

    <section style="padding:16px">
      <div id="info-bar" style="display:flex;gap:28px;flex-wrap:wrap;font-size:.88rem"></div>
    </section>

    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const ticker = "{ticker}";

    fetch('/api/chart-data/' + ticker)
      .then(r => r.json())
      .then(data => {{
        if (data.error) {{
          document.getElementById('status').textContent = 'Error: ' + data.error;
          return;
        }}

        document.getElementById('status').textContent =
          data.bars + ' daily bars  |  ' + data.date_range;

        // Main price chart
        const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
          layout: {{ background: {{ color: '#0a0c14' }}, textColor: '#888' }},
          grid: {{ vertLines: {{ color: '#1a1d2e' }}, horzLines: {{ color: '#1a1d2e' }} }},
          rightPriceScale: {{ borderColor: '#2a2d3e' }},
          timeScale: {{ borderColor: '#2a2d3e', timeVisible: true }},
          crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
        }});

        const candles = chart.addCandlestickSeries({{
          upColor: '#22c55e', downColor: '#ef4444',
          borderUpColor: '#22c55e', borderDownColor: '#ef4444',
          wickUpColor: '#22c55e', wickDownColor: '#ef4444',
        }});
        candles.setData(data.ohlcv);

        // EMA lines
        const ema5 = chart.addLineSeries({{ color: '#60a5fa', lineWidth: 1, title: 'EMA5' }});
        const ema26 = chart.addLineSeries({{ color: '#f59e0b', lineWidth: 1, title: 'EMA26' }});
        ema5.setData(data.ema5);
        ema26.setData(data.ema26);

        chart.timeScale().fitContent();

        // Volume chart
        const volChart = LightweightCharts.createChart(document.getElementById('volume-chart'), {{
          layout: {{ background: {{ color: '#0a0c14' }}, textColor: '#888' }},
          grid: {{ vertLines: {{ color: '#1a1d2e' }}, horzLines: {{ color: '#1a1d2e' }} }},
          rightPriceScale: {{ borderColor: '#2a2d3e' }},
          timeScale: {{ borderColor: '#2a2d3e', timeVisible: true }},
        }});

        const volSeries = volChart.addHistogramSeries({{
          priceFormat: {{ type: 'volume' }},
          priceScaleId: '',
        }});
        volSeries.priceScale().applyOptions({{ scaleMargins: {{ top: 0.1, bottom: 0 }} }});
        volSeries.setData(data.volume);
        volChart.timeScale().fitContent();

        // Sync time scales
        chart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
          volChart.timeScale().setVisibleLogicalRange(range);
        }});
        volChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
          chart.timeScale().setVisibleLogicalRange(range);
        }});

        // Info bar
        const last = data.ohlcv[data.ohlcv.length - 1];
        const info = document.getElementById('info-bar');
        info.innerHTML = `
          <span><span style="color:#555">Open</span> <strong>${{last.open.toFixed(4)}}</strong></span>
          <span><span style="color:#555">High</span> <strong style="color:#22c55e">${{last.high.toFixed(4)}}</strong></span>
          <span><span style="color:#555">Low</span>  <strong style="color:#ef4444">${{last.low.toFixed(4)}}</strong></span>
          <span><span style="color:#555">Close</span><strong>${{last.close.toFixed(4)}}</strong></span>
          <span><span style="color:#555">Date</span> <strong>${{last.time}}</strong></span>
        `;
      }})
      .catch(e => {{ document.getElementById('status').textContent = 'Failed to load: ' + e; }});
    </script>"""

    return page_wrap(f'Chart — {ticker}', '', content)


@app.route('/api/chart-data/<ticker>')
def chart_data(ticker):
    ticker = ticker.upper()
    try:
        conn = get_connection()
        df = get_ticker_data(conn, ticker)
        conn.close()

        if df is None or df.empty:
            return jsonify({'error': f'No data for {ticker}'})

        # Compute EMAs
        ema5  = df['close'].ewm(span=5,  adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()

        def to_time(ts):
            return ts.strftime('%Y-%m-%d')

        ohlcv = [
            {'time': to_time(ts), 'open': float(r['open']), 'high': float(r['high']),
             'low': float(r['low']), 'close': float(r['close'])}
            for ts, r in df.iterrows()
        ]
        volume = [
            {'time': to_time(ts), 'value': float(r['volume']),
             'color': '#22c55e44' if r['close'] >= r['open'] else '#ef444444'}
            for ts, r in df.iterrows()
        ]
        ema5_data  = [{'time': to_time(ts), 'value': float(v)} for ts, v in ema5.items()]
        ema26_data = [{'time': to_time(ts), 'value': float(v)} for ts, v in ema26.items()]

        return jsonify({
            'ticker': ticker,
            'bars': len(df),
            'date_range': f"{to_time(df.index[0])} → {to_time(df.index[-1])}",
            'ohlcv': ohlcv,
            'volume': volume,
            'ema5': ema5_data,
            'ema26': ema26_data,
        })

    except Exception as e:
        return jsonify({'error': str(e)})


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/')
        error = 'Wrong password.'
    return page_wrap('Login', '', f"""
    <div style="max-width:360px;margin:80px auto">
      <section>
        <h2>Admin Login</h2>
        <form method="POST">
          <input name="password" type="password" placeholder="Password" autofocus
            style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;
                   border-radius:6px;color:#fff;font-size:.95rem;margin-bottom:12px">
          {'<p style="color:#f87171;font-size:.82rem;margin-bottom:10px">' + error + '</p>' if error else ''}
          <button type="submit" class="btn btn-blue" style="width:100%">Login</button>
        </form>
      </section>
    </div>""")


@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')


# ─── Data actions ─────────────────────────────────────────────────────────────

@app.route('/run-daily')
def run_daily():
    if not is_admin():
        return redirect('/')
    start_script_job(os.path.join(BASE_DIR, 'db_daily_update.py'), 'Daily Update')
    return redirect('/')


@app.route('/run-initial')
def run_initial():
    if not is_admin():
        return redirect('/')
    start_script_job(os.path.join(BASE_DIR, 'db_initial_download.py'), 'Initial Download')
    return redirect('/')


# ─── Log view ─────────────────────────────────────────────────────────────────

@app.route('/log-view')
def log_view():
    with _job_lock:
        running = _job_running
    log = get_log().replace('<', '&lt;').replace('>', '&gt;')
    content = f'<section><h2>Last Run Log</h2><pre>{log}</pre></section>'
    return page_wrap('Log', 'log', content, auto_refresh=running)


@app.route('/status')
def status():
    with _job_lock:
        return jsonify({'running': _job_running, 'job': _job_name})


# ─── Jimmy's Stock Picks ──────────────────────────────────────────────────────

@app.route('/picks')
def picks_page():
    positions = get_positions()
    history   = get_history()
    cash      = get_account()
    port_val  = get_portfolio_value(positions)
    total_val = cash + port_val
    total_pnl = total_val - 100_000.0

    # Account summary bar
    pnl_color = '#22c55e' if total_pnl >= 0 else '#ef4444'
    pnl_sign  = '+' if total_pnl >= 0 else ''
    summary = f"""
    <div class="grid4" style="margin-bottom:24px">
      <div class="card">
        <div class="stat-label">Cash Available</div>
        <div class="stat-value" style="font-size:1.3rem">${cash:,.2f}</div>
        <div class="stat-sub">of $100,000 starting balance</div>
      </div>
      <div class="card">
        <div class="stat-label">Portfolio Value</div>
        <div class="stat-value" style="font-size:1.3rem">${port_val:,.2f}</div>
        <div class="stat-sub">{len(positions)} open position{'s' if len(positions)!=1 else ''}</div>
      </div>
      <div class="card">
        <div class="stat-label">Total Value</div>
        <div class="stat-value" style="font-size:1.3rem">${total_val:,.2f}</div>
        <div class="stat-sub">cash + portfolio</div>
      </div>
      <div class="card">
        <div class="stat-label">Total P&amp;L</div>
        <div class="stat-value" style="font-size:1.3rem;color:{pnl_color}">{pnl_sign}${total_pnl:,.2f}</div>
        <div class="stat-sub" style="color:{pnl_color}">{pnl_sign}{total_pnl/1000:.1f}% on $100k</div>
      </div>
    </div>"""

    # Add new pick form (admin only)
    add_form = '' if not is_admin() else """
    <section>
      <h2>Add New Pick</h2>
      <form method="POST" action="/picks/buy" enctype="multipart/form-data">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:12px">
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Ticker *</label>
            <input name="ticker" placeholder="e.g. AAPL" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Shares *</label>
            <input name="shares" type="number" step="0.0001" placeholder="e.g. 100" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Buy Price (USD) *</label>
            <input name="buy_price" type="number" step="0.0001" placeholder="e.g. 150.00" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Target / Take Profit</label>
            <input name="target_price" type="number" step="0.0001" placeholder="e.g. 200.00" style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Why I think it will go up</label>
          <textarea name="reason" rows="3" placeholder="Channel breakout forming, EMA squeeze on weekly..." style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical"></textarea>
        </div>
        <div style="margin-bottom:16px">
          <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">TradingView Chart Screenshot</label>
          <input name="chart_image" type="file" accept="image/*" style="color:#aaa;font-size:.85rem">
        </div>
        <button type="submit" class="btn btn-green">+ Add to Portfolio</button>
      </form>
    </section>"""

    # Open positions
    pos_html = ''
    if positions:
        cards = ''
        for p in positions:
            pnl_c  = '#22c55e' if p['pnl'] >= 0 else '#ef4444'
            sign   = '+' if p['pnl'] >= 0 else ''
            tgt    = f"${fmt_num(p['target_price'])}" if p['target_price'] else '—'
            upside = ''
            if p['target_price']:
                up = (p['target_price'] - p['current_price']) / p['current_price'] * 100
                upside = f"<span style='color:#60a5fa;font-size:.78rem'>({up:+.1f}% to target)</span>"

            img_html = ''
            if p['image_path']:
                img_html = f'<img src="/picks/image/{p["image_path"]}" style="width:100%;border-radius:6px;margin-bottom:12px;border:1px solid #2a2d3e">'

            reason_html = f'<p style="color:#aaa;font-size:.83rem;margin-bottom:12px;line-height:1.5">{p["reason"]}</p>' if p['reason'] else ''

            if is_admin():
                action_html = f"""
                <form method="POST" action="/picks/sell/{p['id']}" style="display:flex;gap:8px;align-items:center">
                  <input name="sell_price" type="number" step="0.0001" value="{p['current_price']:.4f}"
                    style="width:150px;padding:7px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem">
                  <button type="submit" class="btn btn-amber" style="padding:7px 16px"
                    onclick="return confirm('Sell {p['shares']} shares of {p['ticker']}?')">Sell</button>
                  <a href="/chart/{p['ticker']}" class="btn btn-blue" style="padding:7px 14px;font-size:.82rem">Chart</a>
                </form>"""
            else:
                action_html = f'<a href="/chart/{p["ticker"]}" class="btn btn-blue" style="padding:7px 14px;font-size:.82rem">View Chart</a>'

            cards += f"""
            <div class="card" style="margin-bottom:16px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:12px">
                <div>
                  <a href="/chart/{p['ticker']}" style="font-size:1.3rem;font-weight:700;color:#60a5fa">{p['ticker']}</a>
                  <span style="color:#555;font-size:.78rem;margin-left:10px">bought {p['bought_date']}</span>
                </div>
                <span style="font-size:1.1rem;font-weight:700;color:{pnl_c}">{sign}${p['pnl']:,.2f} ({sign}{p['pnl_pct']:.1f}%)</span>
              </div>
              {img_html}
              {reason_html}
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:14px;font-size:.83rem">
                <div><span style="color:#555">Shares</span><br><strong>{fmt_num(p['shares'])}</strong></div>
                <div><span style="color:#555">Buy Price</span><br><strong>${fmt_num(p['buy_price'])}</strong></div>
                <div><span style="color:#555">Current</span><br><strong>${fmt_num(p['current_price'])}</strong></div>
                <div><span style="color:#555">Cost Basis</span><br><strong>${p['cost']:,.2f}</strong></div>
                <div><span style="color:#555">Market Value</span><br><strong>${p['value']:,.2f}</strong></div>
                <div><span style="color:#555">Target</span><br><strong>{tgt}</strong> {upside}</div>
              </div>
              {action_html}
            </div>"""
        pos_html = f'<section><h2>Open Positions ({len(positions)})</h2>{cards}</section>'
    else:
        pos_html = '<section><h2>Open Positions</h2><p class="note">No open positions yet. Add your first pick above!</p></section>'

    # Trade history
    hist_html = ''
    if history:
        rows = ''
        for t in history:
            action_color = '#22c55e' if t['action'] == 'BUY' else '#ef4444'
            pnl_str = ''
            if t['pnl'] is not None:
                pnl_color = '#22c55e' if t['pnl'] >= 0 else '#ef4444'
                pnl_str = f'<span style="color:{pnl_color}">{("+" if t["pnl"]>=0 else "")}${t["pnl"]:,.2f}</span>'
            rows += f"""<tr>
              <td>{t['trade_date']}</td>
              <td><strong style="color:#60a5fa">{t['ticker']}</strong></td>
              <td><span style="color:{action_color};font-weight:700">{t['action']}</span></td>
              <td>{fmt_num(t['shares'])}</td>
              <td>${fmt_num(t['price'])}</td>
              <td>${t['total']:,.2f}</td>
              <td>{pnl_str}</td>
            </tr>"""
        hist_html = f"""
        <section>
          <h2>Trade History</h2>
          <style>
            table{{width:100%;border-collapse:collapse;font-size:.83rem}}
            th{{text-align:left;padding:8px 10px;color:#555;border-bottom:1px solid #2a2d3e;font-weight:500}}
            td{{padding:8px 10px;border-bottom:1px solid #151820}}
            tr:hover td{{background:#1f2235}}
          </style>
          <table>
            <tr><th>Date</th><th>Ticker</th><th>Action</th><th>Shares</th><th>Price</th><th>Total</th><th>P&L</th></tr>
            {rows}
          </table>
        </section>"""

    msg = request.args.get('msg', '')
    msg_html = f'<div style="background:#1a2e1a;border:1px solid #22c55e;border-radius:8px;padding:12px 16px;margin-bottom:20px;color:#86efac">{msg}</div>' if msg else ''
    err = request.args.get('err', '')
    err_html = f'<div class="err-box">{err}</div>' if err else ''

    content = err_html + msg_html + summary + add_form + pos_html + hist_html
    return page_wrap("Jimmy's Picks", 'picks', content)


@app.route('/picks/buy', methods=['POST'])
def picks_buy():
    import uuid
    ticker     = request.form.get('ticker', '').strip().upper()
    shares     = float(request.form.get('shares', 0))
    buy_price  = float(request.form.get('buy_price', 0))
    target     = request.form.get('target_price', '').strip()
    reason     = request.form.get('reason', '').strip()
    target_val = float(target) if target else None

    # Handle image upload
    image_filename = ''
    file = request.files.get('chart_image')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        image_filename = f"{ticker}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, image_filename))

    ok, result = buy_stock(ticker, shares, buy_price, target_val, reason, image_filename)
    if ok:
        return redirect(f'/picks?msg=Bought+{shares}+shares+of+{ticker}+at+${buy_price:.4f}')
    else:
        return redirect(f'/picks?err={result}')


@app.route('/picks/sell/<int:pick_id>', methods=['POST'])
def picks_sell(pick_id):
    if not is_admin():
        return redirect('/picks')
    sell_price = float(request.form.get('sell_price', 0))
    ok, result = sell_stock(pick_id, sell_price)
    if ok:
        sign = '+' if result >= 0 else ''
        return redirect(f'/picks?msg=Position+closed.+P%26L:+{sign}${result:.2f}')
    else:
        return redirect(f'/picks?err={result}')


@app.route('/picks/image/<filename>')
def picks_image(filename):
    return send_from_directory(UPLOADS_DIR, filename)


# ─── Ask Jimmy ────────────────────────────────────────────────────────────────

def ask_auth_form(mode='login'):
    """Shared login/register form HTML."""
    other = 'register' if mode == 'login' else 'login'
    other_label = "Don't have an account? Register" if mode == 'login' else 'Already have an account? Login'
    extra = '<input name="email" type="email" placeholder="Email (optional)" style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem;margin-bottom:10px">' if mode == 'register' else ''
    return f"""
    <div style="max-width:380px;margin:60px auto">
      <section>
        <h2>{'Create Account' if mode == 'register' else 'Login to Ask Jimmy'}</h2>
        <form method="POST" style="margin-top:4px">
          <input name="username" placeholder="Username" required autofocus
            style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem;margin-bottom:10px">
          {extra}
          <input name="password" type="password" placeholder="Password" required
            style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem;margin-bottom:14px">
          <button type="submit" class="btn btn-blue" style="width:100%;margin-bottom:12px">
            {'Create Account' if mode == 'register' else 'Login'}
          </button>
          <a href="/ask/{other}" style="font-size:.8rem;color:#555">{other_label}</a>
        </form>
      </section>
    </div>"""


@app.route('/ask')
def ask_page():
    uid   = current_user_id()
    admin = is_admin()
    questions = get_questions(user_id=uid, admin=admin)

    msg = request.args.get('msg', '')
    err = request.args.get('err', '')
    msg_html = f'<div style="background:#1a2e1a;border:1px solid #22c55e;border-radius:8px;padding:12px 16px;margin-bottom:20px;color:#86efac">{msg}</div>' if msg else ''
    err_html = f'<div class="err-box">{err}</div>' if err else ''

    # Submit form
    if uid or admin:
        submit_section = f"""
        <section>
          <h2>Ask Jimmy to Analyse a Stock</h2>
          <form method="POST" action="/ask/submit">
            <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">
              <input name="ticker" placeholder="Ticker (e.g. AAPL)" required
                style="width:160px;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem"
                oninput="this.value=this.value.toUpperCase()" id="tickerInput">
              <button type="button" class="btn btn-blue" onclick="previewChart()" style="padding:9px 16px">Preview Chart</button>
            </div>
            <div id="chart-preview" style="display:none;margin-bottom:12px">
              <div id="preview-box" style="width:100%;height:300px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px"></div>
            </div>
            <textarea name="question" rows="3" required placeholder="What would you like Jimmy to analyse? (e.g. Is this in a channel? Good entry point?)"
              style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem;resize:vertical;margin-bottom:12px"></textarea>
            <button type="submit" class="btn btn-green">Submit Question</button>
          </form>
        </section>
        <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
        <script>
        let previewChart_ = null;
        function previewChart() {{
          const ticker = document.getElementById('tickerInput').value.trim();
          if (!ticker) return;
          const box = document.getElementById('chart-preview');
          box.style.display = 'block';
          const el = document.getElementById('preview-box');
          el.innerHTML = '<p style="color:#555;padding:20px;font-size:.85rem">Loading ' + ticker + '...</p>';
          if (previewChart_) {{ previewChart_.remove(); previewChart_ = null; }}
          fetch('/api/chart-data/' + ticker)
            .then(r => r.json())
            .then(data => {{
              if (data.error) {{ el.innerHTML = '<p style="color:#f87171;padding:20px">' + data.error + '</p>'; return; }}
              el.innerHTML = '';
              previewChart_ = LightweightCharts.createChart(el, {{
                layout: {{ background: {{ color: '#0a0c14' }}, textColor: '#888' }},
                grid: {{ vertLines: {{ color: '#1a1d2e' }}, horzLines: {{ color: '#1a1d2e' }} }},
                rightPriceScale: {{ borderColor: '#2a2d3e' }},
                timeScale: {{ borderColor: '#2a2d3e' }},
                height: 300,
              }});
              const c = previewChart_.addCandlestickSeries({{
                upColor:'#22c55e',downColor:'#ef4444',
                borderUpColor:'#22c55e',borderDownColor:'#ef4444',
                wickUpColor:'#22c55e',wickDownColor:'#ef4444'
              }});
              c.setData(data.ohlcv);
              const e5  = previewChart_.addLineSeries({{color:'#60a5fa',lineWidth:1}});
              const e26 = previewChart_.addLineSeries({{color:'#f59e0b',lineWidth:1}});
              e5.setData(data.ema5); e26.setData(data.ema26);
              previewChart_.timeScale().fitContent();
            }});
        }}
        </script>"""
    else:
        submit_section = f"""
        <section style="text-align:center;padding:32px">
          <p style="color:#aaa;margin-bottom:16px">Login or create a free account to ask Jimmy to analyse a stock.</p>
          <div style="display:flex;gap:10px;justify-content:center">
            <a href="/ask/login"    class="btn btn-blue">Login</a>
            <a href="/ask/register" class="btn btn-green">Create Account</a>
          </div>
        </section>"""

    # Q&A list
    qa_html = ''
    if questions:
        for q in questions:
            is_pending = q['status'] == 'pending'
            ticker_link = f'<a href="/chart/{q["ticker"]}" style="font-size:1.1rem;font-weight:700;color:#60a5fa">{q["ticker"]}</a>'

            answer_block = ''
            if q['answer']:
                answer_block = f"""
                <div style="background:#0f1f0f;border-left:3px solid #22c55e;border-radius:0 6px 6px 0;padding:14px 16px;margin-top:12px">
                  <div style="font-size:.72rem;color:#22c55e;font-weight:700;margin-bottom:6px">JIMMY'S ANALYSIS · {q['answered_date']}</div>
                  <p style="color:#d1fae5;font-size:.9rem;line-height:1.6;white-space:pre-wrap">{q['answer']}</p>
                </div>"""
            elif is_pending:
                answer_block = "<div style=\"color:#555;font-size:.82rem;margin-top:10px;font-style:italic\">⏳ Awaiting Jimmy's analysis...</div>"

            # Admin answer form
            admin_form = ''
            if admin and is_pending:
                admin_form = f"""
                <form method="POST" action="/ask/answer/{q['id']}" style="margin-top:12px">
                  <textarea name="answer" rows="4" placeholder="Type your analysis here..." required
                    style="width:100%;padding:9px 12px;background:#0a0c14;border:1px solid #22c55e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical;margin-bottom:8px"></textarea>
                  <button type="submit" class="btn btn-green" style="padding:7px 16px;font-size:.82rem">Post Analysis</button>
                </form>"""

            pending_badge = '<span style="background:#2a1f00;color:#f59e0b;font-size:.7rem;padding:2px 8px;border-radius:10px;margin-left:8px">PENDING</span>' if is_pending else ''

            qa_html += f"""
            <div class="card" style="margin-bottom:16px">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap">
                {ticker_link}
                {pending_badge}
                <span style="color:#555;font-size:.75rem;margin-left:auto">asked by <strong style="color:#888">{q['username']}</strong> · {q['created_date']}</span>
              </div>
              <p style="color:#ccc;font-size:.9rem;line-height:1.5;white-space:pre-wrap">{q['question']}</p>
              {answer_block}
              {admin_form}
            </div>"""
    else:
        qa_html = '<div class="card" style="text-align:center;padding:32px;color:#555">No questions yet. Be the first to ask!</div>'

    content = f"""
    {err_html}{msg_html}
    {submit_section}
    <section>
      <h2>{('All Questions' if admin else "Jimmy's Stock Analyses")}</h2>
      {qa_html}
    </section>"""

    return page_wrap("Ask Jimmy", 'ask', content)


@app.route('/ask/submit', methods=['POST'])
def ask_submit():
    uid   = current_user_id()
    uname = current_username()
    if not uid:
        return redirect('/ask/login')
    ticker   = request.form.get('ticker', '').strip().upper()
    question = request.form.get('question', '').strip()
    ok, result = submit_question(uid, uname, ticker, question)
    if ok:
        return redirect('/ask?msg=Question+submitted!+Jimmy+will+analyse+it+soon.')
    return redirect(f'/ask?err={result}')


@app.route('/ask/answer/<int:qid>', methods=['POST'])
def ask_answer(qid):
    if not is_admin():
        return redirect('/ask')
    answer = request.form.get('answer', '').strip()
    if answer:
        answer_question(qid, answer)
    return redirect('/ask?msg=Analysis+posted!')


@app.route('/ask/register', methods=['GET', 'POST'])
def ask_register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        ok, result = register_user(username, email, password)
        if ok:
            session['user_id']  = result
            session['username'] = username
            return redirect('/ask?msg=Welcome+' + username + '!')
        return page_wrap('Register', 'ask', ask_auth_form('register') +
                         f'<p style="color:#f87171;text-align:center;margin-top:-16px;font-size:.85rem">{result}</p>')
    return page_wrap('Register', 'ask', ask_auth_form('register'))


@app.route('/ask/login', methods=['GET', 'POST'])
def ask_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        ok, result = login_user(username, password)
        if ok:
            session['user_id']  = result
            session['username'] = username
            return redirect('/ask')
        return page_wrap('Login', 'ask', ask_auth_form('login') +
                         f'<p style="color:#f87171;text-align:center;margin-top:-16px;font-size:.85rem">{result}</p>')
    return page_wrap('Login', 'ask', ask_auth_form('login'))


@app.route('/ask/logout')
def ask_logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect('/ask')


if __name__ == '__main__':
    app.run(debug=True)
