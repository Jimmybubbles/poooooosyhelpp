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
import uuid
import threading
import subprocess
import json
import pandas as pd
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
from db_fader_scanner import run_fader_scan, load_last_fader_results
from db_picks import (init_tables, get_account, get_positions, get_portfolio_value,
                      get_history, buy_stock, sell_stock, get_daily_changes, UPLOADS_DIR)
from db_ask import (init_tables as init_ask_tables, register_user, login_user,
                    submit_question, answer_question, get_questions, get_username,
                    get_user_stats)
from db_asx import (init_tables as init_asx_tables, ASX_200,
                    get_asx_sparklines_batch, get_asx_latest_prices,
                    get_asx_chart_data, get_tickers_with_data,
                    get_asx_account, get_asx_picks, get_asx_history,
                    get_asx_portfolio_value, buy_asx_stock, sell_asx_stock,
                    get_asx_daily_changes)
from flask import session

RESULTS_DIR = os.path.join(BASE_DIR, 'updated_Results_for_scan')
RANGE_RESULTS_FILE = os.path.join(BASE_DIR, 'buylist', 'range_level_results.json')

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload


def is_admin():
    return session.get('admin') is True

# Init tables on startup
try:
    init_tables()
    init_ask_tables()
    init_asx_tables()
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


# ─── Sector performance helper ────────────────────────────────────────────────

SECTOR_ETFS = [
    ('XLK',  'Technology'),
    ('XLF',  'Financials'),
    ('XLE',  'Energy'),
    ('XLV',  'Healthcare'),
    ('XLI',  'Industrials'),
    ('XLY',  'Cons. Discretionary'),
    ('XLC',  'Communications'),
    ('XLP',  'Cons. Staples'),
    ('XLRE', 'Real Estate'),
    ('XLU',  'Utilities'),
    ('XLB',  'Materials'),
]

INDEX_ETFS = [
    ('SPY',  'S&P 500'),
    ('QQQ',  'Nasdaq 100'),
    ('DIA',  'Dow Jones'),
    ('IWM',  'Russell 2000'),
    ('SMH',  'Semiconductors'),
    ('XBI',  'Biotech'),
    ('GDX',  'Gold Miners'),
]

MACRO_INSTRUMENTS = [
    ('DX-Y.NYB', 'US Dollar (DXY)'),
    ('GC=F',     'Gold'),
    ('SI=F',     'Silver'),
    ('HG=F',     'Copper'),
    ('CL=F',     'Crude Oil'),
    ('^TNX',     'US 10Y Yield'),
]

def get_perf_data(tickers):
    """
    Returns {ticker: {d1, w1, m1, m3}} % change for each ticker.
    Pulls last 65 trading days of closes in one query.
    """
    result = {t: {'d1': None, 'w1': None, 'm1': None, 'm3': None} for t in tickers}
    try:
        conn = get_connection()
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ticker, date, close
                FROM prices
                WHERE ticker IN ({fmt})
                  AND date >= DATE_SUB(CURDATE(), INTERVAL 95 DAY)
                ORDER BY ticker, date ASC
            """, [t.upper() for t in tickers])
            rows = cur.fetchall()
        conn.close()

        from collections import defaultdict
        grouped = defaultdict(list)
        for ticker, _, close in rows:
            grouped[ticker.upper()].append(float(close))

        def pct(closes, n):
            if len(closes) > n:
                return (closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100
            return None

        for ticker in tickers:
            closes = grouped.get(ticker.upper(), [])
            if len(closes) >= 2:
                result[ticker]['d1'] = pct(closes, 1)
            if len(closes) >= 6:
                result[ticker]['w1'] = pct(closes, 5)
            if len(closes) >= 22:
                result[ticker]['m1'] = pct(closes, 21)
            if len(closes) >= 64:
                result[ticker]['m3'] = pct(closes, 63)
    except Exception:
        pass
    return result


def perf_color(val):
    """Return background color based on % change magnitude."""
    if val is None:
        return '#1a1d2e'
    if val >= 5:    return '#166534'
    if val >= 3:    return '#15803d'
    if val >= 1.5:  return '#16a34a'
    if val >= 0.5:  return '#22c55e44'
    if val >= 0:    return '#22c55e22'
    if val >= -0.5: return '#ef444422'
    if val >= -1.5: return '#ef444444'
    if val >= -3:   return '#dc2626'
    if val >= -5:   return '#b91c1c'
    return '#7f1d1d'


def perf_text_color(val):
    if val is None: return '#555'
    return '#fff' if abs(val) >= 1.5 else ('#86efac' if val >= 0 else '#fca5a5')


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


def _run_range_scan_job():
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Range Level Scan ===\nStarted: {datetime.now()}\n\n")
    try:
        from RangeLevelScanner import get_range_info, count_ranges_from_pivot, calculate_fader
        from EFI_Indicator import EFI_Indicator

        conn = get_connection()
        tickers = []
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")
            tickers = [r[0] for r in cur.fetchall()]
        conn.close()

        with open(LOG_FILE, 'a') as f:
            f.write(f"Scanning {len(tickers)} tickers from DB...\n\n")

        setups = []
        for i, ticker in enumerate(tickers):
            try:
                conn = get_connection()
                df_raw = get_ticker_data(conn, ticker)
                conn.close()

                if df_raw is None or len(df_raw) < 70:
                    continue

                # Normalise column names to match scanner expectations
                df = df_raw.rename(columns={
                    'open': 'Open', 'high': 'High', 'low': 'Low',
                    'close': 'Close', 'volume': 'Volume'
                })
                df.index.name = 'Date'

                current_idx = len(df) - 1
                current_price = float(df['Close'].iloc[current_idx])

                if current_price < 0.50:
                    continue

                range_info = get_range_info(current_price)
                if range_info is None or range_info['zone'] not in ('NEAR_25', 'NEAR_75'):
                    continue

                indicator = EFI_Indicator()
                efi = indicator.calculate(df)
                current_fi_color   = efi['fi_color'].iloc[current_idx]
                current_force      = efi['force_index'].iloc[current_idx]
                current_norm_price = efi['normalized_price'].iloc[current_idx]

                fader_color = calculate_fader(df, current_idx)

                pivot_low, pivot_date, ranges_traveled = count_ranges_from_pivot(df, current_idx, lookback=60)
                if ranges_traveled >= 3:
                    continue

                if range_info['zone'] == 'NEAR_25':
                    trade_type   = 'WITHIN_RANGE'
                    entry_level  = range_info['levels']['L25']
                    stop_level   = range_info['levels']['L0']
                    target_level = range_info['levels']['L75']
                else:
                    trade_type   = 'RANGE_CHANGE'
                    entry_level  = range_info['levels']['L75']
                    stop_level   = range_info['levels']['L50']
                    next_low     = range_info['range_high']
                    target_level = next_low + range_info['range_size'] * 0.25

                risk   = entry_level - stop_level
                reward = target_level - entry_level
                rr_ratio = reward / risk if risk > 0 else 0

                quality_score = 0
                signal_notes  = []

                if fader_color == 'green':
                    quality_score += 25
                    signal_notes.append('Fader GREEN')
                if current_fi_color in ('lime', 'green'):
                    quality_score += 25
                    signal_notes.append('EFI bullish')
                elif current_fi_color == 'orange' and current_force > efi['force_index'].iloc[current_idx - 1]:
                    quality_score += 15
                    signal_notes.append('EFI improving')

                level_target = range_info['levels']['L25'] if trade_type == 'WITHIN_RANGE' else range_info['levels']['L75']
                dist_pct = abs(current_price - level_target) / range_info['range_size'] * 100
                if dist_pct < 5:
                    quality_score += 20
                    signal_notes.append('Tight to level')
                elif dist_pct < 10:
                    quality_score += 10

                if rr_ratio >= 2:
                    quality_score += 15
                    signal_notes.append(f"R:R {rr_ratio:.1f}")
                elif rr_ratio >= 1.5:
                    quality_score += 10

                if ranges_traveled < 1:
                    quality_score += 15
                    signal_notes.append('Fresh move')
                elif ranges_traveled < 2:
                    quality_score += 10

                if quality_score < 30:
                    continue

                setups.append({
                    'ticker': ticker,
                    'date': df.index[-1].strftime('%m/%d/%Y'),
                    'price': current_price,
                    'trade_type': trade_type,
                    'range_low': range_info['range_low'],
                    'range_high': range_info['range_high'],
                    'range_size': range_info['range_size'],
                    'position_pct': range_info['position_pct'],
                    'zone': range_info['zone'],
                    'L0': range_info['levels']['L0'],
                    'L25': range_info['levels']['L25'],
                    'L50': range_info['levels']['L50'],
                    'L75': range_info['levels']['L75'],
                    'L100': range_info['levels']['L100'],
                    'entry_level': entry_level,
                    'stop_level': stop_level,
                    'target_level': target_level,
                    'risk': risk,
                    'reward': reward,
                    'rr_ratio': rr_ratio,
                    'fader_color': fader_color,
                    'efi_color': current_fi_color,
                    'quality_score': quality_score,
                    'signal_notes': signal_notes,
                    'sparkline': df['Close'].tolist()[-40:],
                })

            except Exception:
                continue

            if (i + 1) % 100 == 0:
                with open(LOG_FILE, 'a') as f:
                    f.write(f"  {i+1}/{len(tickers)} scanned, {len(setups)} found so far\n")

        setups.sort(key=lambda x: x['price'])
        os.makedirs(os.path.dirname(RANGE_RESULTS_FILE), exist_ok=True)
        with open(RANGE_RESULTS_FILE, 'w') as f:
            json.dump({'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                       'results': setups}, f)
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nDone! Found {len(setups)} setups.\nFinished: {datetime.now()}\n")
    except Exception as e:
        import traceback
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nERROR: {e}\n{traceback.format_exc()}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name = ''


def start_range_scan_job():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name = 'Range Scan'
    t = threading.Thread(target=_run_range_scan_job, daemon=True)
    t.start()
    return True


def _run_asx_download_job():
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== ASX Data Download ===\nStarted: {datetime.now()}\n\n")
    try:
        import yfinance as yf
        import traceback as tb
        conn = get_connection()
        ok = 0
        errors = 0
        for i, ticker in enumerate(ASX_200):
            try:
                yf_ticker = ticker + '.AX'
                hist = yf.Ticker(yf_ticker).history(period='2y', interval='1d', auto_adjust=True)
                if hist is None or hist.empty:
                    continue
                # Flatten MultiIndex columns if present
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = [c[0] for c in hist.columns]
                rows = []
                for date, row in hist.iterrows():
                    try:
                        o = float(row['Open'])
                        h = float(row['High'])
                        l = float(row['Low'])
                        c = float(row['Close'])
                        v = int(row['Volume']) if pd.notna(row['Volume']) else 0
                        rows.append((ticker, date.strftime('%Y-%m-%d'), o, h, l, c, v))
                    except Exception:
                        continue
                if not rows:
                    continue
                with conn.cursor() as cur:
                    cur.executemany("""
                        INSERT INTO asx_prices (ticker, date, open, high, low, close, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            open=VALUES(open), high=VALUES(high), low=VALUES(low),
                            close=VALUES(close), volume=VALUES(volume)
                    """, rows)
                conn.commit()
                ok += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    with open(LOG_FILE, 'a') as f:
                        f.write(f"  ERROR {ticker}: {e}\n")
                continue

            if (i + 1) % 20 == 0:
                with open(LOG_FILE, 'a') as f:
                    f.write(f"  {i+1}/{len(ASX_200)} done — {ok} saved, {errors} errors\n")

        conn.close()
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nDone! {ok}/{len(ASX_200)} tickers saved.\nFinished: {datetime.now()}\n")
    except Exception as e:
        import traceback
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nFATAL ERROR: {e}\n{traceback.format_exc()}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name = ''


def start_asx_download_job():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name = 'ASX Download'
    t = threading.Thread(target=_run_asx_download_job, daemon=True)
    t.start()
    return True


def load_range_results():
    if not os.path.exists(RANGE_RESULTS_FILE):
        return None
    try:
        with open(RANGE_RESULTS_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def sparkline_svg(closes, width=120, height=36):
    """Render a tiny inline SVG line chart from a list of close prices."""
    if len(closes) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    mn, mx = min(closes), max(closes)
    if mn == mx:
        return f'<svg width="{width}" height="{height}"></svg>'
    pad = 2
    pts = []
    n = len(closes)
    for i, c in enumerate(closes):
        x = pad + i / (n - 1) * (width - pad * 2)
        y = pad + (1 - (c - mn) / (mx - mn)) * (height - pad * 2)
        pts.append(f"{x:.1f},{y:.1f}")
    color = '#22c55e' if closes[-1] >= closes[0] else '#ef4444'
    return (f'<svg width="{width}" height="{height}" style="display:block;vertical-align:middle">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
            f'</svg>')


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
        {lnk('/range','Range Levels','range')}
        {lnk('/asx','ASX 200','asx')}
        {lnk('/asx/picks','ASX Picks','asxpicks')}
        {lnk('/fader','Fader Scan','fader')}
        {lnk('/indexes','Indexes & ETFs','indexes')}
        {lnk('/log-view','Log','log')}
        {lnk('/admin/analytics','Analytics','analytics') if is_admin() else ''}
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

    # ── US portfolio ──────────────────────────────────────────────────────────
    positions    = get_positions()
    history      = get_history()
    cash         = get_account()
    port_val     = get_portfolio_value(positions)
    total_val    = cash + port_val
    total_pnl    = total_val - 100_000.0
    closed       = [t for t in history if t['pnl'] is not None]
    wins         = [t for t in closed if t['pnl'] > 0]
    win_rate     = (len(wins) / len(closed) * 100) if closed else 0
    total_realised = sum(t['pnl'] for t in closed)

    # ── ASX portfolio ─────────────────────────────────────────────────────────
    asx_positions = get_asx_picks()
    asx_cash      = get_asx_account()
    asx_port_val  = get_asx_portfolio_value(asx_positions)
    asx_total_val = asx_cash + asx_port_val
    asx_total_pnl = asx_total_val - 100_000.0
    asx_open_pnl  = sum(p['pnl'] for p in asx_positions)

    with _job_lock:
        running = _job_running

    err = f'<div class="err-box"><strong>DB Error:</strong> {stats["error"]}</div>' if stats['error'] else ''

    last_refresh   = get_last_refresh_date()
    refreshed_today = already_refreshed_today()

    if not is_admin():
        daily_btn = initial_btn = refresh_btn = ''
    elif running:
        daily_btn   = '<span class="btn btn-off">Run Daily Update</span>'
        initial_btn = '<span class="btn btn-off">Run Initial Download</span>'
        refresh_btn = '<span class="btn btn-off">⏳ Updating prices…</span>'
    elif refreshed_today:
        refresh_btn = f'<span class="btn btn-off" style="background:#14532d;color:#86efac;cursor:default">✓ Prices updated today</span>'
        daily_btn   = '<a href="/run-daily" class="btn btn-blue">Run Daily Update</a>'
        initial_btn = '<a href="/run-initial" class="btn btn-amber" onclick="return confirm(\'This takes 1–2 hours. Continue?\')">Run Initial Download</a>'
    else:
        refresh_btn = '<a href="/run-refresh" class="btn btn-green" style="font-size:.95rem;padding:10px 22px">⟳ Update US &amp; ASX Prices</a>'
        daily_btn   = '<a href="/run-daily" class="btn btn-blue">Run Daily Update</a>'
        initial_btn = '<a href="/run-initial" class="btn btn-amber" onclick="return confirm(\'This takes 1–2 hours. Continue?\')">Run Initial Download</a>'

    refresh_note = f'Last updated: {last_refresh}' if last_refresh else 'Never updated today'

    def pnl_html(val):
        c = '#22c55e' if val >= 0 else '#ef4444'
        s = '+' if val >= 0 else ''
        return f'<span style="color:{c};font-weight:700">{s}${val:,.2f}</span>'

    def pnl_pct_html(val, basis=100_000):
        c = '#22c55e' if val >= 0 else '#ef4444'
        s = '+' if val >= 0 else ''
        return f'<span style="color:{c};font-size:.85rem">{s}{val/basis*100:.2f}%</span>'

    wr_color = '#22c55e' if win_rate >= 50 else '#ef4444'
    rp_color = '#22c55e' if total_realised >= 0 else '#ef4444'
    rp_sign  = '+' if total_realised >= 0 else ''

    # ── US open positions P&L rows ────────────────────────────────────────────
    def pos_rows(pos_list, link_prefix='/chart/'):
        rows = ''
        for p in sorted(pos_list, key=lambda x: x['pnl'], reverse=True):
            pc = '#22c55e' if p['pnl'] >= 0 else '#ef4444'
            ps = '+' if p['pnl'] >= 0 else ''
            rows += f"""<tr>
              <td><a href="{link_prefix}{p['ticker']}" style="color:#60a5fa;font-weight:700">{p['ticker']}</a></td>
              <td style="color:#aaa">{p.get('bought_date','')}</td>
              <td style="color:#fff">${p['current_price']:.2f}</td>
              <td style="color:#555">${p['buy_price']:.2f}</td>
              <td style="color:{pc};font-weight:600">{ps}${p['pnl']:,.2f}</td>
              <td style="color:{pc}">{ps}{p['pnl_pct']:.1f}%</td>
            </tr>"""
        return rows

    us_pos_rows  = pos_rows(positions)
    asx_pos_rows = pos_rows(asx_positions)

    pos_table_style = """
      <style>
        .pos-table{width:100%;border-collapse:collapse;font-size:.82rem}
        .pos-table th{text-align:left;padding:7px 10px;color:#555;border-bottom:1px solid #2a2d3e;font-weight:500}
        .pos-table td{padding:7px 10px;border-bottom:1px solid #151820}
        .pos-table tr:hover td{background:#1f2235}
      </style>"""

    us_table = (f'{pos_table_style}<table class="pos-table">'
                f'<tr><th>Ticker</th><th>Bought</th><th>Price</th><th>Cost</th><th>P&L $</th><th>P&L %</th></tr>'
                f'{us_pos_rows}</table>') if us_pos_rows else '<p class="note">No open positions.</p>'

    asx_table = (f'<table class="pos-table">'
                 f'<tr><th>Ticker</th><th>Bought</th><th>Price</th><th>Cost</th><th>P&L A$</th><th>P&L %</th></tr>'
                 f'{asx_pos_rows}</table>') if asx_pos_rows else '<p class="note">No open ASX positions.</p>'

    # ── Recent US trade history rows ──────────────────────────────────────────
    hist_rows = ''
    for t in history[:8]:
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
          <td>${fmt_num(t['price'])}</td>
          <td>${t['total']:,.2f}</td>
          <td>{pnl_str}</td>
        </tr>"""

    content = f"""
    {err}
    <style>
      .port-hero {{
        border-radius:12px; padding:24px 28px; margin-bottom:12px;
        border:1px solid #2a2d3e;
      }}
      .port-hero .label {{ font-size:.72rem;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px }}
      .port-hero .total {{ font-size:2.2rem;font-weight:800;color:#fff;margin-bottom:2px }}
      .port-hero .sub   {{ font-size:.88rem }}
      .port-hero .open-pnl {{ font-size:.82rem;color:#777;margin-top:6px }}
    </style>

    <!-- Side-by-side portfolio heroes -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px">

      <!-- US Picks -->
      <div class="port-hero" style="background:linear-gradient(135deg,#1a1d2e 0%,#0f1117 100%)">
        <div class="label">🇺🇸 US Picks — $100k</div>
        <div class="total">${total_val:,.2f}</div>
        <div class="sub">{pnl_html(total_pnl)} &nbsp; {pnl_pct_html(total_pnl)}</div>
        <div class="open-pnl">
          {len(positions)} open &nbsp;·&nbsp;
          Cash ${cash:,.2f} &nbsp;·&nbsp;
          Realised <span style="color:{'#22c55e' if total_realised>=0 else '#ef4444'}">{rp_sign}${total_realised:,.2f}</span>
        </div>
        <div style="margin-top:10px">
          <a href="/picks" style="font-size:.78rem;color:#3b82f6">View picks →</a>
        </div>
      </div>

      <!-- ASX Picks -->
      <div class="port-hero" style="background:linear-gradient(135deg,#1a2420 0%,#0f1117 100%)">
        <div class="label">🇦🇺 ASX Picks — A$100k</div>
        <div class="total">A${asx_total_val:,.2f}</div>
        <div class="sub">{pnl_html(asx_total_pnl)} &nbsp; {pnl_pct_html(asx_total_pnl)}</div>
        <div class="open-pnl">
          {len(asx_positions)} open &nbsp;·&nbsp;
          Cash A${asx_cash:,.2f} &nbsp;·&nbsp;
          Unrealised {pnl_html(asx_open_pnl)}
        </div>
        <div style="margin-top:10px">
          <a href="/asx/picks" style="font-size:.78rem;color:#3b82f6">View picks →</a>
        </div>
      </div>

    </div>

    <!-- Stats row -->
    <div class="grid4" style="margin-bottom:24px">
      <div class="card">
        <div class="stat-label">US Cash</div>
        <div class="stat-value" style="font-size:1.4rem">${cash:,.2f}</div>
        <div class="stat-sub">{len(positions)} open positions</div>
      </div>
      <div class="card">
        <div class="stat-label">ASX Cash</div>
        <div class="stat-value" style="font-size:1.4rem">A${asx_cash:,.2f}</div>
        <div class="stat-sub">{len(asx_positions)} open positions</div>
      </div>
      <div class="card">
        <div class="stat-label">US Win Rate</div>
        <div class="stat-value" style="font-size:1.4rem;color:{wr_color}">{win_rate:.0f}%</div>
        <div class="stat-sub">{len(wins)} wins / {len(closed)} closed</div>
      </div>
      <div class="card">
        <div class="stat-label">US Realised P&amp;L</div>
        <div class="stat-value" style="font-size:1.4rem;color:{rp_color}">{rp_sign}${total_realised:,.2f}</div>
        <div class="stat-sub">from closed trades</div>
      </div>
    </div>

    <!-- Open positions side by side -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px">
      <section style="margin:0">
        <h2>US Open Positions
          <a href="/picks" style="font-size:.75rem;font-weight:400;color:#3b82f6;text-transform:none;margin-left:8px;letter-spacing:0">manage →</a>
        </h2>
        {us_table}
      </section>
      <section style="margin:0">
        <h2>ASX Open Positions
          <a href="/asx/picks" style="font-size:.75rem;font-weight:400;color:#3b82f6;text-transform:none;margin-left:8px;letter-spacing:0">manage →</a>
        </h2>
        {asx_table}
      </section>
    </div>

    <!-- Recent US trades -->
    <section style="margin-bottom:24px">
      <h2>Recent US Trades <a href="/picks" style="font-size:.75rem;font-weight:400;color:#3b82f6;text-transform:none;margin-left:10px;letter-spacing:0">View all →</a></h2>
      <style>
        .trade-table{{width:100%;border-collapse:collapse;font-size:.83rem}}
        .trade-table th{{text-align:left;padding:8px 10px;color:#555;border-bottom:1px solid #2a2d3e;font-weight:500}}
        .trade-table td{{padding:8px 10px;border-bottom:1px solid #151820}}
        .trade-table tr:hover td{{background:#1f2235}}
      </style>
      {'<table class="trade-table"><tr><th>Date</th><th>Ticker</th><th>Action</th><th>Price</th><th>Total</th><th>P&L</th></tr>' + hist_rows + '</table>' if hist_rows else '<p class="note">No trades yet. <a href="/picks">Add your first pick →</a></p>'}
    </section>

    <!-- Admin data actions -->
    {f'''<section>
      <h2>Price Data</h2>
      <div class="btn-row" style="margin-bottom:10px">
        {refresh_btn}
      </div>
      <p class="note">{refresh_note} &nbsp;·&nbsp; Updates both US and ASX prices in one go.</p>
      <details style="margin-top:12px">
        <summary style="font-size:.75rem;color:#444;cursor:pointer">Advanced options</summary>
        <div class="btn-row" style="margin-top:10px">
          {daily_btn}
          {initial_btn}
        </div>
        <p class="note">US only · Initial download takes 1–2 hours.</p>
      </details>
    </section>''' if is_admin() else ''}
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

    # Batch-fetch last 40 closes for all tickers in one query
    all_tickers = [r['ticker'] for r in results]
    sparklines = {}
    try:
        fmt = ','.join(['%s'] * len(all_tickers))
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ticker, date, close
                FROM prices
                WHERE ticker IN ({fmt})
                ORDER BY ticker, date ASC
            """, all_tickers)
            for ticker, _, close in cur.fetchall():
                sparklines.setdefault(ticker, []).append(float(close))
        conn.close()
        # Keep only last 40
        sparklines = {t: v[-40:] for t, v in sparklines.items()}
    except Exception:
        pass

    def rows_html(items):
        html = ''
        for r in items:
            w = '✓' if r['weekly'] else '–'
            d = '✓' if r['daily']  else '–'
            score_color = '#22c55e' if r['score'] == 2 else '#f59e0b'
            svg = sparkline_svg(sparklines.get(r['ticker'], []))
            html += f"""
            <tr class="res-row" data-ticker="{r['ticker']}" style="cursor:pointer">
              <td>
                <div style="display:flex;align-items:center;gap:10px">
                  <strong style="color:#60a5fa;min-width:52px">{r['ticker']}</strong>
                  {svg}
                </div>
              </td>
              <td data-val="{r['price']}">${r['price']:,.4f}</td>
              <td data-val="{r['score']}"><span style="color:{score_color};font-weight:700">{r['score']}/2</span></td>
              <td style="color:{'#22c55e' if r['weekly'] else '#555'}">{w}</td>
              <td style="color:{'#22c55e' if r['daily'] else '#555'}">{d}</td>
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

    chart_js = """
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    document.querySelectorAll('.res-row').forEach(row => {
      row.addEventListener('click', () => {
        const ticker = row.dataset.ticker;
        const existId = 'rdrop-' + ticker;
        const exist = document.getElementById(existId);

        if (exist) {
          exist.remove();
          row.classList.remove('active');
          return;
        }

        document.querySelectorAll('.res-drop').forEach(d => d.remove());
        document.querySelectorAll('.res-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');

        const drop = document.createElement('tr');
        drop.id = existId;
        drop.className = 'res-drop';
        drop.innerHTML = `<td colspan="5" style="background:#080a10;padding:16px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <span style="color:#fff;font-weight:700;font-size:1rem">${ticker}</span>
            <span style="color:#555;font-size:.75rem" id="rs-${ticker}">Loading...</span>
            <a href="/chart/${ticker}" style="font-size:.78rem;color:#60a5fa;margin-left:16px">Open full chart →</a>
          </div>
          <div id="rm-${ticker}" style="height:360px;background:#0a0c14;border-radius:6px"></div>
          <div id="rv-${ticker}" style="height:70px;background:#0a0c14;border-radius:6px;margin-top:3px"></div>
        </td>`;
        row.parentNode.insertBefore(drop, row.nextSibling);

        fetch('/api/chart-data/' + ticker)
          .then(r => r.json())
          .then(data => {
            if (data.error) { document.getElementById('rs-' + ticker).textContent = data.error; return; }
            document.getElementById('rs-' + ticker).textContent = data.bars + ' bars · ' + data.date_range;

            const chart = LightweightCharts.createChart(document.getElementById('rm-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: true },
              crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            });
            const candles = chart.addCandlestickSeries({
              upColor: '#22c55e', downColor: '#ef4444',
              borderUpColor: '#22c55e', borderDownColor: '#ef4444',
              wickUpColor: '#22c55e', wickDownColor: '#ef4444',
            });
            candles.setData(data.ohlcv);
            const ema5  = chart.addLineSeries({ color: '#60a5fa', lineWidth: 1, title: 'EMA5' });
            const ema26 = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'EMA26' });
            ema5.setData(data.ema5);
            ema26.setData(data.ema26);
            chart.timeScale().fitContent();

            const volChart = LightweightCharts.createChart(document.getElementById('rv-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: false },
            });
            const volS = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
            volS.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
            volS.setData(data.volume);
            volChart.timeScale().fitContent();

            chart.timeScale().subscribeVisibleLogicalRangeChange(r => volChart.timeScale().setVisibleLogicalRange(r));
            volChart.timeScale().subscribeVisibleLogicalRangeChange(r => chart.timeScale().setVisibleLogicalRange(r));
          })
          .catch(e => { document.getElementById('rs-' + ticker).textContent = 'Failed: ' + e; });
      });
    });
    </script>"""

    def make_section(title, items):
        if not items:
            return ''
        return f"""
        <section style="margin-bottom:20px">
          <h2>{title} <span style="color:#555;font-size:.75rem;font-weight:400;text-transform:none;letter-spacing:0">— click a row to expand chart</span></h2>
          {table_style}
          <table>
            <thead><tr>
              <th onclick="sortTable(this)">Ticker</th>
              <th onclick="sortTable(this)" class="sort-desc">Price</th>
              <th onclick="sortTable(this)">Score</th>
              <th>Weekly</th><th>Daily</th>
            </tr></thead>
            <tbody>{rows_html(items)}</tbody>
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

    content = summary + make_section(f'BOTH — Daily + Weekly Channel ({len(both_rows)} stocks)', both_rows) + \
              make_section(f'SINGLE — One Timeframe ({len(single_rows)} stocks)', single_rows) + chart_js
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

REFRESH_DATE_FILE = os.path.join(BASE_DIR, 'last_refresh_date.txt')


def get_last_refresh_date():
    """Return the date string of the last successful refresh, or None."""
    try:
        with open(REFRESH_DATE_FILE) as f:
            return f.read().strip()
    except Exception:
        return None


def set_last_refresh_date():
    from datetime import date
    with open(REFRESH_DATE_FILE, 'w') as f:
        f.write(date.today().isoformat())


def already_refreshed_today():
    from datetime import date
    return get_last_refresh_date() == date.today().isoformat()


def _run_refresh_job():
    """Update prices only for tickers with open positions (US + ASX). Fast."""
    global _job_running, _job_name
    import yfinance as yf
    from datetime import date, timedelta

    def log(msg):
        with open(LOG_FILE, 'a') as f:
            f.write(msg)

    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Picks Price Refresh ===\nStarted: {datetime.now()}\n\n")
    try:
        conn = get_connection()

        # ── US open positions ─────────────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM picks WHERE status='open'")
            us_tickers = [r[0] for r in cur.fetchall()]

        log(f"US open positions: {', '.join(us_tickers) if us_tickers else 'none'}\n")
        for ticker in us_tickers:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(date) FROM prices WHERE ticker=%s", (ticker,))
                    last = cur.fetchone()[0]
                start = (last + timedelta(days=1)) if last else (date.today() - timedelta(days=365))
                end   = date.today() + timedelta(days=1)
                df    = yf.download(ticker, start=start, end=end,
                                    interval='1d', auto_adjust=True, progress=False)
                if df.empty:
                    log(f"  {ticker}: no new data\n")
                    continue
                if hasattr(df.columns, 'get_level_values'):
                    df.columns = df.columns.get_level_values(0)
                rows = []
                for dt, row in df.iterrows():
                    rows.append((ticker.upper(), str(dt.date()),
                                 float(row['Open']), float(row['High']),
                                 float(row['Low']),  float(row['Close']),
                                 int(row['Volume']) if not pd.isna(row['Volume']) else 0))
                with conn.cursor() as cur:
                    cur.executemany("""
                        INSERT INTO prices (ticker,date,open,high,low,close,volume)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                          open=VALUES(open),high=VALUES(high),low=VALUES(low),
                          close=VALUES(close),volume=VALUES(volume)
                    """, rows)
                conn.commit()
                log(f"  {ticker}: updated {len(rows)} rows\n")
            except Exception as e:
                log(f"  {ticker}: ERROR — {e}\n")

        # ── ASX open positions ────────────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM asx_picks WHERE status='open'")
            asx_tickers = [r[0] for r in cur.fetchall()]

        log(f"\nASX open positions: {', '.join(asx_tickers) if asx_tickers else 'none'}\n")
        for ticker in asx_tickers:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(date) FROM asx_prices WHERE ticker=%s", (ticker,))
                    last = cur.fetchone()[0]
                start    = (last + timedelta(days=1)) if last else (date.today() - timedelta(days=365))
                end      = date.today() + timedelta(days=1)
                yf_ticker = ticker + '.AX'
                df = yf.download(yf_ticker, start=start, end=end,
                                 interval='1d', auto_adjust=True, progress=False)
                if df.empty:
                    log(f"  {ticker}: no new data\n")
                    continue
                if hasattr(df.columns, 'get_level_values'):
                    df.columns = df.columns.get_level_values(0)
                rows = []
                for dt, row in df.iterrows():
                    rows.append((ticker.upper(), str(dt.date()),
                                 float(row['Open']), float(row['High']),
                                 float(row['Low']),  float(row['Close']),
                                 int(row['Volume']) if not pd.isna(row['Volume']) else 0))
                with conn.cursor() as cur:
                    cur.executemany("""
                        INSERT INTO asx_prices (ticker,date,open,high,low,close,volume)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                          open=VALUES(open),high=VALUES(high),low=VALUES(low),
                          close=VALUES(close),volume=VALUES(volume)
                    """, rows)
                conn.commit()
                log(f"  {ticker}: updated {len(rows)} rows\n")
            except Exception as e:
                log(f"  {ticker}: ERROR — {e}\n")

        conn.close()
        set_last_refresh_date()
        log(f"\nDone: {datetime.now()}\n")

    except Exception as e:
        log(f"\nFATAL ERROR: {e}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name    = ''


def start_refresh_job():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name    = 'Data Refresh'
    threading.Thread(target=_run_refresh_job, daemon=True).start()
    return True


@app.route('/run-refresh')
def run_refresh():
    if not is_admin():
        return redirect('/')
    if not already_refreshed_today():
        start_refresh_job()
    return redirect('/')


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

    # Daily P&L — compare today's close vs yesterday's close for each position
    daily_changes = get_daily_changes([p['ticker'] for p in positions])
    daily_pnl_total = sum(
        p['shares'] * (daily_changes[p['ticker']][0] - daily_changes[p['ticker']][1])
        for p in positions if p['ticker'] in daily_changes
    )
    for p in positions:
        if p['ticker'] in daily_changes:
            today, prev = daily_changes[p['ticker']]
            p['daily_pnl'] = p['shares'] * (today - prev)
            p['daily_pct'] = ((today - prev) / prev * 100) if prev else 0
        else:
            p['daily_pnl'] = 0.0
            p['daily_pct'] = 0.0

    # Account summary bar
    pnl_color  = '#22c55e' if total_pnl >= 0 else '#ef4444'
    pnl_sign   = '+' if total_pnl >= 0 else ''
    dpnl_color = '#22c55e' if daily_pnl_total >= 0 else '#ef4444'
    dpnl_sign  = '+' if daily_pnl_total >= 0 else ''
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
        <div class="stat-label">Total P&amp;L</div>
        <div class="stat-value" style="font-size:1.3rem;color:{pnl_color}">{pnl_sign}${total_pnl:,.2f}</div>
        <div class="stat-sub" style="color:{pnl_color}">{pnl_sign}{total_pnl/1000:.1f}% on $100k</div>
      </div>
      <div class="card">
        <div class="stat-label">Today's P&amp;L</div>
        <div class="stat-value" style="font-size:1.3rem;color:{dpnl_color}">{dpnl_sign}${daily_pnl_total:,.2f}</div>
        <div class="stat-sub" style="color:{dpnl_color}">unrealised daily move</div>
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

            dc     = p['daily_pnl']
            dc_c   = '#22c55e' if dc >= 0 else '#ef4444'
            dc_s   = '+' if dc >= 0 else ''
            daily_badge = f'<span style="font-size:.78rem;font-weight:600;color:{dc_c};background:{dc_c}18;padding:2px 8px;border-radius:4px">{dc_s}${dc:,.2f} today ({dc_s}{p["daily_pct"]:.2f}%)</span>'

            cards += f"""
            <div class="card" style="margin-bottom:16px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                <div>
                  <a href="/chart/{p['ticker']}" style="font-size:1.3rem;font-weight:700;color:#60a5fa">{p['ticker']}</a>
                  <span style="color:#555;font-size:.78rem;margin-left:10px">bought {p['bought_date']}</span>
                </div>
                <span style="font-size:1.1rem;font-weight:700;color:{pnl_c}">{sign}${p['pnl']:,.2f} ({sign}{p['pnl_pct']:.1f}%)</span>
              </div>
              <div style="margin-bottom:12px">{daily_badge}</div>
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


# ─── Range Level Scanner ──────────────────────────────────────────────────────

@app.route('/range')
def range_page():
    data = load_range_results()
    with _job_lock:
        running = _job_running
        jname = _job_name

    if is_admin():
        if running and jname == 'Range Scan':
            run_btn = '<span class="btn btn-off">Scanning...</span>'
        elif running:
            run_btn = '<span class="btn btn-off">Another job running</span>'
        else:
            run_btn = '<a href="/range/run" class="btn btn-green">▶ Run Range Scan</a>'
    else:
        run_btn = ''

    if not data:
        content = f"""
        <section>
          <h2>Range Level Scanner</h2>
          <p style="color:#aaa;margin-bottom:16px;font-size:.9rem">
            Finds stocks at 25% and 75% of their price range — natural settling zones
            with built-in 1:2 R:R.<br>
            <strong style="color:#fff">WITHIN_RANGE</strong> = enter at 25%, target 75%.
            <strong style="color:#fff">RANGE_CHANGE</strong> = enter at 75%, target next 25%.
          </p>
          <div class="btn-row">{run_btn}</div>
          <p class="note" style="margin-top:12px">No scan results yet. Run the scanner to see setups.</p>
        </section>"""
        return page_wrap('Range Levels', 'range', content, auto_refresh=(running and jname == 'Range Scan'))

    results = data['results']
    within = [r for r in results if r['trade_type'] == 'WITHIN_RANGE']
    change = [r for r in results if r['trade_type'] == 'RANGE_CHANGE']

    def build_rows(items):
        html = ''
        for r in items:
            svg = sparkline_svg(r.get('sparkline', []))
            type_color = '#22c55e' if r['trade_type'] == 'WITHIN_RANGE' else '#a78bfa'
            zone_label = '25% Zone' if r['zone'] == 'NEAR_25' else '75% Zone'
            score_color = '#22c55e' if r['quality_score'] >= 60 else ('#f59e0b' if r['quality_score'] >= 40 else '#ef4444')
            fader_color = '#22c55e' if r['fader_color'] == 'green' else ('#ef4444' if r['fader_color'] == 'red' else '#555')
            efi_color = '#22c55e' if r['efi_color'] in ('lime','green') else '#555'
            levels_json = json.dumps({
                'entry': r['entry_level'], 'stop': r['stop_level'],
                'target': r['target_level'],
                'L0': r['L0'], 'L25': r['L25'], 'L50': r['L50'],
                'L75': r['L75'], 'L100': r['L100']
            }).replace('"', '&quot;')
            html += f"""<tr class="range-row" data-ticker="{r['ticker']}" data-levels="{levels_json}"
                         style="cursor:pointer">
              <td>
                <div style="display:flex;align-items:center;gap:10px">
                  <strong style="color:#60a5fa;font-size:.95rem;min-width:52px">{r['ticker']}</strong>
                  {svg}
                </div>
              </td>
              <td style="font-weight:700">${r['price']:.2f}</td>
              <td><span style="color:{type_color};font-size:.78rem;font-weight:600">{r['trade_type'].replace('_',' ')}</span></td>
              <td style="color:#aaa;font-size:.82rem">{zone_label}</td>
              <td style="color:#22c55e">${r['entry_level']:.2f}</td>
              <td style="color:#ef4444">${r['stop_level']:.2f}</td>
              <td style="color:#60a5fa">${r['target_level']:.2f}</td>
              <td style="font-weight:600">{r['rr_ratio']:.1f}x</td>
              <td><span style="color:{fader_color};font-size:.8rem">{'●' if r['fader_color']=='green' else ('●' if r['fader_color']=='red' else '○')} {r['fader_color'].title()}</span></td>
              <td><span style="color:{efi_color};font-size:.8rem">{r['efi_color'].title()}</span></td>
              <td><span style="color:{score_color};font-weight:700">{r['quality_score']}</span></td>
            </tr>"""
        return html

    table_style = """
    <style>
    .rtable { width:100%; border-collapse:collapse; font-size:.84rem; }
    .rtable th { text-align:left; padding:8px 12px; color:#555; border-bottom:1px solid #2a2d3e;
                 font-weight:500; white-space:nowrap; }
    .rtable td { padding:8px 12px; border-bottom:1px solid #151820; vertical-align:middle; }
    .rtable .range-row:hover td { background:#1f2235; }
    .rtable .range-row.active td { background:#1a2235; }
    .chart-drop td { padding:0 !important; }
    </style>"""

    chart_js = """
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const openCharts = {};
    document.querySelectorAll('.range-row').forEach(row => {
      row.addEventListener('click', () => {
        const ticker = row.dataset.ticker;
        const levels = JSON.parse(row.dataset.levels.replace(/&quot;/g, '"'));
        const existId = 'cdrop-' + ticker;
        const exist = document.getElementById(existId);

        // Close if already open
        if (exist) {
          exist.remove();
          row.classList.remove('active');
          if (openCharts[ticker]) { openCharts[ticker].remove(); delete openCharts[ticker]; }
          return;
        }

        // Close any other open chart
        document.querySelectorAll('.chart-drop').forEach(d => d.remove());
        document.querySelectorAll('.range-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');

        // Insert drop row
        const drop = document.createElement('tr');
        drop.id = existId;
        drop.className = 'chart-drop';
        drop.innerHTML = `<td colspan="11" style="background:#080a10;padding:16px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <span style="color:#fff;font-weight:700;font-size:1rem">${ticker}</span>
            <span style="color:#555;font-size:.75rem" id="cstatus-${ticker}">Loading chart...</span>
          </div>
          <div id="cmain-${ticker}" style="height:360px;background:#0a0c14;border-radius:6px"></div>
          <div id="cvol-${ticker}" style="height:70px;background:#0a0c14;border-radius:6px;margin-top:3px"></div>
          <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:10px;font-size:.78rem">
            <span style="color:#22c55e">━ Entry $${levels.entry.toFixed(2)}</span>
            <span style="color:#ef4444">╌ Stop $${levels.stop.toFixed(2)}</span>
            <span style="color:#60a5fa">╌ Target $${levels.target.toFixed(2)}</span>
            <span style="color:#555">┄ 25% $${levels.L25.toFixed(2)} &nbsp;|&nbsp; 75% $${levels.L75.toFixed(2)}</span>
          </div>
        </td>`;
        row.parentNode.insertBefore(drop, row.nextSibling);

        fetch('/api/chart-data/' + ticker)
          .then(r => r.json())
          .then(data => {
            if (data.error) {
              document.getElementById('cstatus-' + ticker).textContent = 'Error: ' + data.error;
              return;
            }
            document.getElementById('cstatus-' + ticker).textContent =
              data.bars + ' bars · ' + data.date_range;

            const chart = LightweightCharts.createChart(
              document.getElementById('cmain-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: true },
              crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            });

            const candles = chart.addCandlestickSeries({
              upColor: '#22c55e', downColor: '#ef4444',
              borderUpColor: '#22c55e', borderDownColor: '#ef4444',
              wickUpColor: '#22c55e', wickDownColor: '#ef4444',
            });
            candles.setData(data.ohlcv);

            // Price level lines
            candles.createPriceLine({ price: levels.entry,  color: '#22c55e', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'Entry' });
            candles.createPriceLine({ price: levels.stop,   color: '#ef4444', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Stop' });
            candles.createPriceLine({ price: levels.target, color: '#60a5fa', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Target' });
            candles.createPriceLine({ price: levels.L25,    color: '#374151', lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '25%' });
            candles.createPriceLine({ price: levels.L75,    color: '#374151', lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '75%' });
            candles.createPriceLine({ price: levels.L50,    color: '#1f2937', lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '50%' });

            const ema5  = chart.addLineSeries({ color: '#60a5fa', lineWidth: 1, title: 'EMA5' });
            const ema26 = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'EMA26' });
            ema5.setData(data.ema5);
            ema26.setData(data.ema26);
            chart.timeScale().fitContent();

            const volChart = LightweightCharts.createChart(
              document.getElementById('cvol-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: false },
            });
            const volS = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
            volS.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
            volS.setData(data.volume);
            volChart.timeScale().fitContent();

            chart.timeScale().subscribeVisibleLogicalRangeChange(r => volChart.timeScale().setVisibleLogicalRange(r));
            volChart.timeScale().subscribeVisibleLogicalRangeChange(r => chart.timeScale().setVisibleLogicalRange(r));

            openCharts[ticker] = chart;
          })
          .catch(e => { document.getElementById('cstatus-' + ticker).textContent = 'Failed: ' + e; });
      });
    });
    </script>"""

    def section_table(title, items, color):
        if not items:
            return ''
        rows = build_rows(items)
        return f"""
        <section style="margin-bottom:20px">
          <h2 style="color:{color}">{title} <span style="color:#555;font-size:.75rem;font-weight:400;text-transform:none;letter-spacing:0">({len(items)} setups) — click a row to expand chart</span></h2>
          {table_style}
          <table class="rtable">
            <thead><tr>
              <th>Ticker</th><th>Price</th><th>Type</th><th>Zone</th>
              <th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th>
              <th>Fader</th><th>EFI</th><th>Score</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>"""

    log_section = ''
    if running and jname == 'Range Scan':
        log_section = f'<section><h2>Live Log</h2><pre>{get_log().replace("<","&lt;")}</pre></section>'

    content = f"""
    <section style="margin-bottom:20px">
      <h2>Range Level Scanner</h2>
      <p style="color:#aaa;margin-bottom:14px;font-size:.88rem">
        Stocks at 25%/75% of their price range — natural settling zones with built-in 1:2 R:R.<br>
        Scan date: <strong style="color:#fff">{data['scan_date']}</strong> &nbsp;·&nbsp;
        {len(results)} total setups &nbsp;·&nbsp;
        {len(within)} WITHIN_RANGE &nbsp;·&nbsp; {len(change)} RANGE_CHANGE
      </p>
      <div class="btn-row">{run_btn}</div>
    </section>
    {log_section}
    {section_table('WITHIN RANGE — Enter 25%, Target 75%', within, '#22c55e')}
    {section_table('RANGE CHANGE — Enter 75%, Target next 25%', change, '#a78bfa')}
    {chart_js}"""

    return page_wrap('Range Levels', 'range', content, auto_refresh=(running and jname == 'Range Scan'))


@app.route('/range/run')
def range_run():
    if not is_admin():
        return redirect('/range')
    start_range_scan_job()
    return redirect('/range')


# ─── ASX 200 ──────────────────────────────────────────────────────────────────

@app.route('/asx')
def asx_page():
    with _job_lock:
        running = _job_running
        jname   = _job_name

    if is_admin():
        if running and jname == 'ASX Download':
            dl_btn = '<span class="btn btn-off">Downloading...</span>'
        elif running:
            dl_btn = '<span class="btn btn-off">Another job running</span>'
        else:
            dl_btn = '<a href="/asx/download" class="btn btn-blue">↓ Download / Update ASX Data</a>'
    else:
        dl_btn = ''

    has_data = bool(get_tickers_with_data())
    if not has_data:
        content = f"""
        <section>
          <h2>ASX 200</h2>
          <p style="color:#aaa;margin-bottom:16px;font-size:.9rem">
            No ASX data in the database yet. Download it first (takes ~5 min).
          </p>
          <div class="btn-row">{dl_btn}</div>
        </section>"""
        return page_wrap('ASX 200', 'asx', content, auto_refresh=(running and jname == 'ASX Download'))

    sparklines  = get_asx_sparklines_batch()
    latest      = get_asx_latest_prices()
    with_data   = get_tickers_with_data()

    rows_html = ''
    for ticker in sorted(ASX_200):
        closes  = sparklines.get(ticker, [])
        price   = latest.get(ticker)
        svg     = sparkline_svg(closes)
        price_s = f'A${price:.3f}' if price else '—'
        has_row = ticker in with_data
        rows_html += f"""
        <tr class="asx-row" data-ticker="{ticker}" style="cursor:{'pointer' if has_row else 'default'}">
          <td>
            <div style="display:flex;align-items:center;gap:10px">
              <strong style="color:#60a5fa;min-width:52px">{ticker}</strong>
              {svg if has_row else ''}
            </div>
          </td>
          <td style="font-weight:600">{price_s}</td>
          <td style="color:#555;font-size:.78rem">ASX</td>
        </tr>"""

    last_log = get_log()
    log_section = ''
    if running and jname == 'ASX Download':
        log_section = f'<section><h2>Download Log (live)</h2><pre>{last_log.replace("<","&lt;")}</pre></section>'
    elif 'ASX Data Download' in last_log:
        log_section = f'<section><h2>Last Download Log</h2><pre>{last_log.replace("<","&lt;")}</pre></section>'

    chart_js = """
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    document.querySelectorAll('.asx-row').forEach(row => {
      row.addEventListener('click', () => {
        const ticker = row.dataset.ticker;
        const existId = 'adrop-' + ticker;
        const exist = document.getElementById(existId);
        if (exist) { exist.remove(); row.classList.remove('active'); return; }
        document.querySelectorAll('.asx-drop').forEach(d => d.remove());
        document.querySelectorAll('.asx-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        const drop = document.createElement('tr');
        drop.id = existId; drop.className = 'asx-drop';
        drop.innerHTML = `<td colspan="3" style="background:#080a10;padding:16px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <span style="color:#fff;font-weight:700;font-size:1rem">${ticker} <span style="color:#555;font-size:.78rem">ASX</span></span>
            <span style="color:#555;font-size:.75rem" id="as-${ticker}">Loading...</span>
          </div>
          <div id="am-${ticker}" style="height:340px;background:#0a0c14;border-radius:6px"></div>
          <div id="av-${ticker}" style="height:65px;background:#0a0c14;border-radius:6px;margin-top:3px"></div>
        </td>`;
        row.parentNode.insertBefore(drop, row.nextSibling);
        fetch('/api/asx-chart/' + ticker)
          .then(r => r.json())
          .then(data => {
            if (data.error) { document.getElementById('as-' + ticker).textContent = data.error; return; }
            document.getElementById('as-' + ticker).textContent = data.bars + ' bars · ' + data.date_range;
            const chart = LightweightCharts.createChart(document.getElementById('am-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: true },
              crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            });
            const candles = chart.addCandlestickSeries({
              upColor: '#22c55e', downColor: '#ef4444',
              borderUpColor: '#22c55e', borderDownColor: '#ef4444',
              wickUpColor: '#22c55e', wickDownColor: '#ef4444',
            });
            candles.setData(data.ohlcv);
            const ema5  = chart.addLineSeries({ color: '#60a5fa', lineWidth: 1, title: 'EMA5' });
            const ema26 = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'EMA26' });
            ema5.setData(data.ema5); ema26.setData(data.ema26);
            chart.timeScale().fitContent();
            const vc = LightweightCharts.createChart(document.getElementById('av-' + ticker), {
              layout: { background: { color: '#0a0c14' }, textColor: '#888' },
              grid: { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
              rightPriceScale: { borderColor: '#2a2d3e' },
              timeScale: { borderColor: '#2a2d3e', timeVisible: false },
            });
            const vs = vc.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
            vs.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
            vs.setData(data.volume); vc.timeScale().fitContent();
            chart.timeScale().subscribeVisibleLogicalRangeChange(r => vc.timeScale().setVisibleLogicalRange(r));
            vc.timeScale().subscribeVisibleLogicalRangeChange(r => chart.timeScale().setVisibleLogicalRange(r));
          })
          .catch(e => { document.getElementById('as-' + ticker).textContent = 'Failed: ' + e; });
      });
    });
    </script>"""

    content = f"""
    <section style="margin-bottom:20px">
      <h2>ASX 200 <span style="color:#555;font-weight:400;font-size:.8rem;text-transform:none;letter-spacing:0">({len(with_data)} tickers with data · click row to expand chart)</span></h2>
      <div class="btn-row" style="margin-bottom:0">{dl_btn}</div>
    </section>
    {log_section}
    <section>
      <style>
        .asx-table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
        .asx-table th {{ text-align:left; padding:8px 12px; color:#555;
                        border-bottom:1px solid #2a2d3e; font-weight:500; cursor:pointer; user-select:none; }}
        .asx-table th:hover {{ color:#aaa; }}
        .asx-table th.sort-asc::after  {{ content:' ▲'; font-size:.65rem; color:#60a5fa; }}
        .asx-table th.sort-desc::after {{ content:' ▼'; font-size:.65rem; color:#60a5fa; }}
        .asx-table td {{ padding:8px 12px; border-bottom:1px solid #151820; vertical-align:middle; }}
        .asx-table .asx-row:hover td {{ background:#1f2235; }}
        .asx-table .asx-row.active td {{ background:#1a2235; }}
        .asx-drop td {{ padding:0 !important; }}
      </style>
      <table class="asx-table">
        <thead><tr>
          <th onclick="sortAsx(this)">Ticker</th>
          <th onclick="sortAsx(this)">Price (AUD)</th>
          <th>Market</th>
        </tr></thead>
        <tbody id="asx-tbody">{rows_html}</tbody>
      </table>
    </section>
    <script>
    function sortAsx(th) {{
      const tbody = document.getElementById('asx-tbody');
      const idx = th.cellIndex;
      const asc = th.classList.contains('sort-desc');
      th.closest('thead').querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      const rows = Array.from(tbody.querySelectorAll('.asx-row'));
      rows.sort((a, b) => {{
        const av = a.cells[idx].textContent.trim();
        const bv = b.cells[idx].textContent.trim();
        const an = parseFloat(av.replace('A$','')), bn = parseFloat(bv.replace('A$',''));
        const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
        return asc ? cmp : -cmp;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }}
    </script>
    {chart_js}"""

    return page_wrap('ASX 200', 'asx', content, auto_refresh=(running and jname == 'ASX Download'))


@app.route('/asx/download')
def asx_download():
    if not is_admin():
        return redirect('/asx')
    start_asx_download_job()
    return redirect('/asx')


@app.route('/api/asx-chart/<ticker>')
def asx_chart_api(ticker):
    ticker = ticker.upper()
    rows = get_asx_chart_data(ticker)
    if not rows:
        return jsonify({'error': f'No data for {ticker}'})

    dates  = [str(r[0]) for r in rows]
    opens  = [float(r[1]) for r in rows]
    highs  = [float(r[2]) for r in rows]
    lows   = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    vols   = [int(r[5]) if r[5] else 0 for r in rows]

    close_s = pd.Series(closes)
    ema5  = close_s.ewm(span=5,  adjust=False).mean().tolist()
    ema26 = close_s.ewm(span=26, adjust=False).mean().tolist()

    ohlcv  = [{'time': dates[i], 'open': opens[i], 'high': highs[i],
               'low': lows[i], 'close': closes[i]} for i in range(len(dates))]
    volume = [{'time': dates[i], 'value': vols[i],
               'color': '#22c55e44' if closes[i] >= opens[i] else '#ef444444'}
              for i in range(len(dates))]
    e5  = [{'time': dates[i], 'value': ema5[i]}  for i in range(len(dates))]
    e26 = [{'time': dates[i], 'value': ema26[i]} for i in range(len(dates))]

    return jsonify({
        'ohlcv': ohlcv, 'volume': volume, 'ema5': e5, 'ema26': e26,
        'bars': len(ohlcv),
        'date_range': f"{dates[0]} → {dates[-1]}" if dates else '',
    })


# ─── ASX Picks ────────────────────────────────────────────────────────────────

@app.route('/asx/picks')
def asx_picks_page():
    positions = get_asx_picks()
    history   = get_asx_history()
    cash      = get_asx_account()
    port_val  = get_asx_portfolio_value(positions)
    total_val = cash + port_val
    total_pnl = total_val - 100_000.0

    # Daily P&L — compare today's close vs yesterday's close for each position
    daily_changes = get_asx_daily_changes([p['ticker'] for p in positions])
    daily_pnl_total = sum(
        p['shares'] * (daily_changes[p['ticker']][0] - daily_changes[p['ticker']][1])
        for p in positions if p['ticker'] in daily_changes
    )
    for p in positions:
        if p['ticker'] in daily_changes:
            today, prev = daily_changes[p['ticker']]
            p['daily_pnl'] = p['shares'] * (today - prev)
            p['daily_pct'] = ((today - prev) / prev * 100) if prev else 0
        else:
            p['daily_pnl'] = 0.0
            p['daily_pct'] = 0.0

    # Account summary bar
    pnl_color  = '#22c55e' if total_pnl >= 0 else '#ef4444'
    pnl_sign   = '+' if total_pnl >= 0 else ''
    dpnl_color = '#22c55e' if daily_pnl_total >= 0 else '#ef4444'
    dpnl_sign  = '+' if daily_pnl_total >= 0 else ''
    summary = f"""
    <div class="grid4" style="margin-bottom:24px">
      <div class="card">
        <div class="stat-label">Cash Available</div>
        <div class="stat-value" style="font-size:1.3rem">A${cash:,.2f}</div>
        <div class="stat-sub">of A$100,000 starting balance</div>
      </div>
      <div class="card">
        <div class="stat-label">Portfolio Value</div>
        <div class="stat-value" style="font-size:1.3rem">A${port_val:,.2f}</div>
        <div class="stat-sub">{len(positions)} open position{'s' if len(positions)!=1 else ''}</div>
      </div>
      <div class="card">
        <div class="stat-label">Total P&amp;L</div>
        <div class="stat-value" style="font-size:1.3rem;color:{pnl_color}">{pnl_sign}A${total_pnl:,.2f}</div>
        <div class="stat-sub" style="color:{pnl_color}">{pnl_sign}{total_pnl/1000:.1f}% on A$100k</div>
      </div>
      <div class="card">
        <div class="stat-label">Today's P&amp;L</div>
        <div class="stat-value" style="font-size:1.3rem;color:{dpnl_color}">{dpnl_sign}A${daily_pnl_total:,.2f}</div>
        <div class="stat-sub" style="color:{dpnl_color}">unrealised daily move</div>
      </div>
    </div>"""

    # Add new pick form (admin only)
    add_form = '' if not is_admin() else """
    <section>
      <h2>Add New ASX Pick</h2>
      <form method="POST" action="/asx/picks/buy" enctype="multipart/form-data">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:12px">
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Ticker *</label>
            <input name="ticker" placeholder="e.g. BHP" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Shares *</label>
            <input name="shares" type="number" step="0.0001" placeholder="e.g. 100" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Buy Price (AUD) *</label>
            <input name="buy_price" type="number" step="0.0001" placeholder="e.g. 45.00" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Target / Take Profit</label>
            <input name="target_price" type="number" step="0.0001" placeholder="e.g. 55.00" style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
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
        <button type="submit" class="btn btn-green">+ Add to ASX Portfolio</button>
      </form>
    </section>"""

    # Open positions
    pos_html = ''
    if positions:
        cards = ''
        for p in positions:
            pnl_c  = '#22c55e' if p['pnl'] >= 0 else '#ef4444'
            sign   = '+' if p['pnl'] >= 0 else ''
            tgt    = f"A${fmt_num(p['target_price'])}" if p['target_price'] else '—'
            upside = ''
            if p['target_price']:
                up = (p['target_price'] - p['current_price']) / p['current_price'] * 100
                upside = f"<span style='color:#60a5fa;font-size:.78rem'>({up:+.1f}% to target)</span>"

            img_html = ''
            if p['image_path']:
                img_html = f'<img src="/asx/picks/image/{p["image_path"]}" style="width:100%;border-radius:6px;margin-bottom:12px;border:1px solid #2a2d3e">'

            reason_html = f'<p style="color:#aaa;font-size:.83rem;margin-bottom:12px;line-height:1.5">{p["reason"]}</p>' if p['reason'] else ''

            if is_admin():
                action_html = f"""
                <form method="POST" action="/asx/picks/sell/{p['id']}" style="display:flex;gap:8px;align-items:center">
                  <input name="sell_price" type="number" step="0.0001" value="{p['current_price']:.4f}"
                    style="width:150px;padding:7px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem">
                  <button type="submit" class="btn btn-amber" style="padding:7px 16px"
                    onclick="return confirm('Sell {p['shares']} shares of {p['ticker']}?')">Sell</button>
                </form>"""
            else:
                action_html = ''

            dc     = p['daily_pnl']
            dc_c   = '#22c55e' if dc >= 0 else '#ef4444'
            dc_s   = '+' if dc >= 0 else ''
            daily_badge = f'<span style="font-size:.78rem;font-weight:600;color:{dc_c};background:{dc_c}18;padding:2px 8px;border-radius:4px">{dc_s}A${dc:,.2f} today ({dc_s}{p["daily_pct"]:.2f}%)</span>'

            cards += f"""
            <div class="card" style="margin-bottom:16px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                <div>
                  <span style="font-size:1.3rem;font-weight:700;color:#60a5fa">{p['ticker']}</span>
                  <span style="color:#555;font-size:.78rem;margin-left:10px">ASX · bought {p['bought_date']}</span>
                </div>
                <span style="font-size:1.1rem;font-weight:700;color:{pnl_c}">{sign}A${p['pnl']:,.2f} ({sign}{p['pnl_pct']:.1f}%)</span>
              </div>
              <div style="margin-bottom:12px">{daily_badge}</div>
              {img_html}
              {reason_html}
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:14px;font-size:.83rem">
                <div><span style="color:#555">Shares</span><br><strong>{fmt_num(p['shares'])}</strong></div>
                <div><span style="color:#555">Buy Price</span><br><strong>A${fmt_num(p['buy_price'])}</strong></div>
                <div><span style="color:#555">Current</span><br><strong>A${fmt_num(p['current_price'])}</strong></div>
                <div><span style="color:#555">Cost Basis</span><br><strong>A${p['cost']:,.2f}</strong></div>
                <div><span style="color:#555">Market Value</span><br><strong>A${p['value']:,.2f}</strong></div>
                <div><span style="color:#555">Target</span><br><strong>{tgt}</strong> {upside}</div>
              </div>
              {action_html}
            </div>"""
        pos_html = f'<section><h2>Open Positions ({len(positions)})</h2>{cards}</section>'
    else:
        pos_html = '<section><h2>Open Positions</h2><p class="note">No open positions yet. Add your first ASX pick above!</p></section>'

    # Trade history
    hist_html = ''
    if history:
        rows = ''
        for t in history:
            action_color = '#22c55e' if t['action'] == 'BUY' else '#ef4444'
            pnl_str = ''
            if t['pnl'] is not None:
                pnl_color = '#22c55e' if t['pnl'] >= 0 else '#ef4444'
                pnl_str = f'<span style="color:{pnl_color}">{("+" if t["pnl"]>=0 else "")}A${t["pnl"]:,.2f}</span>'
            rows += f"""<tr>
              <td>{t['trade_date']}</td>
              <td><strong style="color:#60a5fa">{t['ticker']}</strong></td>
              <td><span style="color:{action_color};font-weight:700">{t['action']}</span></td>
              <td>{fmt_num(t['shares'])}</td>
              <td>A${fmt_num(t['price'])}</td>
              <td>A${t['total']:,.2f}</td>
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
    return page_wrap("Jimmy's ASX Picks", 'asxpicks', content)


@app.route('/asx/picks/buy', methods=['POST'])
def asx_picks_buy():
    if not is_admin():
        return redirect('/asx/picks')
    ticker     = request.form.get('ticker', '').strip().upper()
    shares     = float(request.form.get('shares', 0))
    buy_price  = float(request.form.get('buy_price', 0))
    target     = request.form.get('target_price', '').strip()
    reason     = request.form.get('reason', '').strip()
    target_val = float(target) if target else None

    image_filename = ''
    file = request.files.get('chart_image')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        image_filename = f"asx_{ticker}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, image_filename))

    ok, result = buy_asx_stock(ticker, shares, buy_price, target_val, reason, image_filename)
    if ok:
        return redirect(f'/asx/picks?msg=Bought+{shares}+shares+of+{ticker}+at+A${buy_price:.4f}')
    return redirect(f'/asx/picks?err={result}')


@app.route('/asx/picks/image/<filename>')
def asx_picks_image(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@app.route('/asx/picks/sell/<int:pick_id>', methods=['POST'])
def asx_picks_sell(pick_id):
    if not is_admin():
        return redirect('/asx/picks')
    sell_price = float(request.form.get('sell_price', 0))
    ok, result = sell_asx_stock(pick_id, sell_price)
    if ok:
        sign = '+' if result >= 0 else ''
        return redirect(f'/asx/picks?msg=Sold+position+P%26L+{sign}A${result:.2f}')
    return redirect(f'/asx/picks?err={result}')


# ─── Fader Scanner ────────────────────────────────────────────────────────────

def _run_fader_scan_job():
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Fader Scan ===\nStarted: {datetime.now()}\n\n")
    try:
        run_fader_scan(log_callback=lambda m: open(LOG_FILE, 'a').write(m))
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nERROR: {e}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name    = ''


def start_fader_scan():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name    = 'Fader Scan'
    threading.Thread(target=_run_fader_scan_job, daemon=True).start()
    return True


@app.route('/fader')
def fader_page():
    with _job_lock:
        running = _job_running

    last = load_last_fader_results()

    run_btn = ''
    spinner = ''
    if is_admin():
        if running:
            run_btn = '<span class="btn btn-off">⏳ Scan Running…</span>'
            spinner = """
            <div id="scanner-spinner" style="text-align:center;padding:48px 20px">
              <style>
                @keyframes spin  { to { transform: rotate(360deg); } }
                @keyframes pulse { 0%,100%{opacity:.3} 50%{opacity:1} }
                @keyframes ticker-scroll {
                  0%   { content: "Scanning tickers…"; }
                  33%  { content: "Crunching channels…"; }
                  66%  { content: "Checking fader signals…"; }
                  100% { content: "Almost there…"; }
                }
                .spin-ring {
                  width: 72px; height: 72px; margin: 0 auto 24px;
                  border: 5px solid #2a2d3e;
                  border-top-color: #3b82f6;
                  border-right-color: #22c55e;
                  border-radius: 50%;
                  animation: spin 1s linear infinite;
                }
                .spin-dot {
                  display: inline-block; width: 8px; height: 8px;
                  border-radius: 50%; background: #3b82f6; margin: 0 3px;
                  animation: pulse 1.2s ease-in-out infinite;
                }
                .spin-dot:nth-child(2) { animation-delay: .2s; background:#22c55e; }
                .spin-dot:nth-child(3) { animation-delay: .4s; background:#f59e0b; }
              </style>
              <div class="spin-ring"></div>
              <div style="font-size:1rem;font-weight:600;color:#fff;margin-bottom:8px">
                Running Fader Scan
              </div>
              <div style="font-size:.83rem;color:#555;margin-bottom:16px" id="scan-msg">
                Scanning up to 3000+ tickers through 3 filters…
              </div>
              <div>
                <span class="spin-dot"></span>
                <span class="spin-dot"></span>
                <span class="spin-dot"></span>
              </div>
              <div style="margin-top:20px;font-size:.75rem;color:#444">
                Page auto-refreshes every 5s · results appear when done
              </div>
            </div>
            <script>
              const messages = [
                "Scanning up to 3000+ tickers through 3 filters…",
                "① Checking channel squeeze (EMA5/EMA26/ATR)…",
                "② Calculating fader signal (JMA + WMA chain)…",
                "③ Finding stocks at 25% of their dollar range…",
                "Sorting by closest to the 25% level…",
                "Almost done, hang tight…"
              ];
              let idx = 0;
              const el = document.getElementById('scan-msg');
              setInterval(() => {
                idx = (idx + 1) % messages.length;
                el.style.opacity = 0;
                setTimeout(() => { el.textContent = messages[idx]; el.style.opacity = 1; }, 300);
              }, 3000);
              el.style.transition = 'opacity 0.3s';
            </script>"""
        else:
            run_btn = '<a href="/run-fader" class="btn btn-blue">▶ Run Fader Scan</a>'

    # Build results table
    table = ''
    scan_info = ''
    if last:
        scan_info = (f'<p class="note" style="margin-bottom:16px">'
                     f'Last scan: {last["scan_date"]} — '
                     f'<strong style="color:#fff">{last["total"]}</strong> setups found</p>')
        if last['results']:
            rows = ''
            for r in last['results']:
                rows += f"""<tr>
                  <td><a href="/chart/{r['ticker']}" style="color:#60a5fa;font-weight:700">{r['ticker']}</a></td>
                  <td style="color:#fff">${r['price']:.2f}</td>
                  <td style="color:#aaa">{r['range']}</td>
                  <td style="color:#f59e0b">{r['position_pct']:.1f}%</td>
                  <td style="color:#86efac">${r['L25']:.2f}</td>
                  <td style="color:#22c55e">${r['L75']:.2f}</td>
                  <td style="color:#ef4444">${r['L0']:.2f}</td>
                  <td style="color:#22c55e;font-weight:600">{r['rr']:.1f}x</td>
                </tr>"""
            table = f"""
            <style>
              .fader-table {{ width:100%; border-collapse:collapse; font-size:.83rem }}
              .fader-table th {{ text-align:left; padding:8px 12px; color:#555;
                                 border-bottom:1px solid #2a2d3e; font-weight:500 }}
              .fader-table td {{ padding:8px 12px; border-bottom:1px solid #151820 }}
              .fader-table tr:hover td {{ background:#1f2235 }}
            </style>
            <table class="fader-table">
              <tr>
                <th>Ticker</th><th>Price</th><th>Range</th><th>Pos%</th>
                <th>25% Level</th><th>Target 75%</th><th>Stop 0%</th><th>R:R</th>
              </tr>
              {rows}
            </table>"""
        else:
            table = '<p class="note">No setups found in last scan.</p>'

    content = f"""
    <div style="margin-bottom:20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      {run_btn}
      <span style="font-size:.78rem;color:#555">
        Conditions: channel printing (daily) · fader green · price at 25% of dollar range
      </span>
    </div>
    {spinner}

    <section style="margin-bottom:20px">
      <h2>How it works</h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;font-size:.83rem">
        <div class="card" style="padding:14px">
          <div style="color:#3b82f6;font-weight:700;margin-bottom:6px">① Channel</div>
          <div style="color:#aaa">EMA(5)/EMA(26) compressed within ATR — stock is coiling, low volatility squeeze</div>
        </div>
        <div class="card" style="padding:14px">
          <div style="color:#22c55e;font-weight:700;margin-bottom:6px">② Fader Green</div>
          <div style="color:#aaa">Fader line rising — JMA + WMA-chain signal turning bullish inside the squeeze</div>
        </div>
        <div class="card" style="padding:14px">
          <div style="color:#f59e0b;font-weight:700;margin-bottom:6px">③ 25% of Range</div>
          <div style="color:#aaa">Price sitting at the natural settling level — e.g. $1.25 in the $1–$2 range. Target: 75% level</div>
        </div>
      </div>
    </section>

    <section>
      <h2>Fader Scan Results</h2>
      {scan_info}
      {table if table else '<p class="note">No scan run yet. Click Run Fader Scan above.</p>'}
    </section>
    """
    return page_wrap('Fader Scan', 'fader', content, auto_refresh=running)


@app.route('/run-fader')
def run_fader_route():
    if not is_admin():
        return redirect('/fader')
    start_fader_scan()
    return redirect('/fader')


# ─── Indexes & ETFs ───────────────────────────────────────────────────────────

@app.route('/indexes')
def indexes_page():
    # ── Performance heatmap data from DB ──────────────────────────────────────
    all_tickers = ([t for t, _ in SECTOR_ETFS] + [t for t, _ in INDEX_ETFS]
                   + [t for t, _ in MACRO_INSTRUMENTS])
    perf = get_perf_data(all_tickers)

    def heatmap_row(ticker, name, p):
        cells = ''
        for key in ('d1', 'w1', 'm1', 'm3'):
            v   = p[key]
            bg  = perf_color(v)
            tc  = perf_text_color(v)
            txt = f'{("+" if v and v>=0 else "")}{v:.2f}%' if v is not None else '—'
            cells += (f'<td style="background:{bg};color:{tc};text-align:center;'
                      f'padding:9px 6px;font-size:.82rem;font-weight:600;'
                      f'border-right:1px solid #0f1117">{txt}</td>')
        return (f'<tr style="border-bottom:1px solid #0f1117">'
                f'<td style="padding:9px 12px;font-weight:600;white-space:nowrap">{ticker}</td>'
                f'<td style="padding:9px 12px;color:#888;font-size:.8rem;white-space:nowrap">{name}</td>'
                f'{cells}</tr>')

    sector_rows = ''.join(heatmap_row(t, n, perf[t]) for t, n in SECTOR_ETFS)
    index_rows  = ''.join(heatmap_row(t, n, perf[t]) for t, n in INDEX_ETFS)
    macro_rows  = ''.join(heatmap_row(t, n, perf[t]) for t, n in MACRO_INSTRUMENTS)

    heatmap_table = lambda rows: f"""
        <table style="width:100%;border-collapse:collapse;font-size:.83rem">
          <thead>
            <tr style="border-bottom:2px solid #2a2d3e">
              <th style="text-align:left;padding:8px 12px;color:#555;font-weight:500;width:70px">Ticker</th>
              <th style="text-align:left;padding:8px 12px;color:#555;font-weight:500">Sector / Name</th>
              <th style="text-align:center;padding:8px 10px;color:#555;font-weight:500;width:80px">1 Day</th>
              <th style="text-align:center;padding:8px 10px;color:#555;font-weight:500;width:80px">1 Week</th>
              <th style="text-align:center;padding:8px 10px;color:#555;font-weight:500;width:80px">1 Month</th>
              <th style="text-align:center;padding:8px 10px;color:#555;font-weight:500;width:80px">3 Month</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    content = f"""
    <style>
      .tf-btn {{
        padding: 7px 20px; border-radius: 6px; font-size: .85rem; font-weight: 600;
        cursor: pointer; border: none; background: #252839; color: #aaa;
        transition: background .15s, color .15s;
      }}
      .tf-btn.active {{ background: #3b82f6; color: #fff; }}
      .tf-btn:hover:not(.active) {{ background: #2e3250; color: #ddd; }}
      .ix-section {{ margin-bottom: 32px; }}
      .ix-section h2 {{ font-size: .78rem; font-weight: 600; color: #777;
                       text-transform: uppercase; letter-spacing: .06em; margin-bottom: 14px; }}
      .ix-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
        gap: 12px;
      }}
      .ix-cell {{
        background: #1a1d2e; border: 1px solid #2a2d3e; border-radius: 8px;
        overflow: hidden; height: 240px;
      }}
    </style>

    <!-- ── Performance Heatmap ─────────────────────────────────────────── -->
    <div class="ix-section">
      <h2>Dollar, Commodities &amp; Rates</h2>
      <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;overflow:hidden">
        {heatmap_table(macro_rows)}
      </div>
    </div>

    <div class="ix-section">
      <h2>Sector ETF Performance</h2>
      <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;overflow:hidden">
        {heatmap_table(sector_rows)}
      </div>
    </div>

    <div class="ix-section">
      <h2>Index &amp; Thematic ETF Performance</h2>
      <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;overflow:hidden">
        {heatmap_table(index_rows)}
      </div>
    </div>

    <!-- ── TradingView Charts ──────────────────────────────────────────── -->
    <div style="margin-bottom:24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span style="font-size:.78rem;color:#555;text-transform:uppercase;letter-spacing:.08em;margin-right:4px">Chart Timeframe</span>
      <button onclick="switchTF('1D')" id="btn-1D" class="tf-btn active">1 Day</button>
      <button onclick="switchTF('1W')" id="btn-1W" class="tf-btn">1 Week</button>
      <button onclick="switchTF('1M')" id="btn-1M" class="tf-btn">1 Month</button>
      <button onclick="switchTF('3M')" id="btn-3M" class="tf-btn">3 Month</button>
    </div>

    <div class="ix-section">
      <h2>Major Indexes</h2>
      <div class="ix-grid" id="grid-indexes"></div>
    </div>

    <div class="ix-section">
      <h2>Dollar &amp; Commodities</h2>
      <div class="ix-grid" id="grid-macro"></div>
    </div>

    <div class="ix-section">
      <h2>US Sector ETFs</h2>
      <div class="ix-grid" id="grid-sectors"></div>
    </div>

    <script>
      const GROUPS = {{
        'indexes': [
          {{ symbol: 'AMEX:SPY',      name: 'S&P 500 (SPY)'       }},
          {{ symbol: 'NASDAQ:QQQ',    name: 'Nasdaq 100 (QQQ)'    }},
          {{ symbol: 'AMEX:DIA',      name: 'Dow Jones (DIA)'     }},
          {{ symbol: 'AMEX:IWM',      name: 'Russell 2000 (IWM)'  }},
          {{ symbol: 'CBOE:VIX',      name: 'VIX'                 }},
        ],
        'macro': [
          {{ symbol: 'TVC:DXY',    name: 'US Dollar (DXY)'  }},
          {{ symbol: 'TVC:GOLD',   name: 'Gold'             }},
          {{ symbol: 'TVC:SILVER', name: 'Silver'           }},
          {{ symbol: 'TVC:COPPER', name: 'Copper'           }},
          {{ symbol: 'TVC:USOIL',  name: 'Crude Oil'        }},
          {{ symbol: 'TVC:US10Y',  name: 'US 10Y Yield'     }},
        ],
        'sectors': [
          {{ symbol: 'AMEX:XLK',      name: 'Technology (XLK)'          }},
          {{ symbol: 'AMEX:XLF',      name: 'Financials (XLF)'          }},
          {{ symbol: 'AMEX:XLE',      name: 'Energy (XLE)'              }},
          {{ symbol: 'AMEX:XLV',      name: 'Healthcare (XLV)'          }},
          {{ symbol: 'AMEX:XLI',      name: 'Industrials (XLI)'         }},
          {{ symbol: 'AMEX:XLY',      name: 'Cons. Discretionary (XLY)' }},
          {{ symbol: 'AMEX:XLC',      name: 'Communications (XLC)'      }},
          {{ symbol: 'AMEX:XLP',      name: 'Cons. Staples (XLP)'       }},
          {{ symbol: 'AMEX:XLRE',     name: 'Real Estate (XLRE)'        }},
          {{ symbol: 'AMEX:XLU',      name: 'Utilities (XLU)'           }},
          {{ symbol: 'AMEX:XLB',      name: 'Materials (XLB)'           }},
          {{ symbol: 'AMEX:XBI',      name: 'Biotech (XBI)'             }},
          {{ symbol: 'AMEX:SMH',      name: 'Semiconductors (SMH)'      }},
          {{ symbol: 'AMEX:GDX',      name: 'Gold Miners (GDX)'         }},
        ]
      }};

      function loadWidget(cell, symbol, dateRange) {{
        cell.innerHTML = '';
        const wrapper = document.createElement('div');
        wrapper.className = 'tradingview-widget-container';
        wrapper.style.height = '100%';
        const inner = document.createElement('div');
        inner.className = 'tradingview-widget-container__widget';
        inner.style.height = '100%';
        wrapper.appendChild(inner);
        const script = document.createElement('script');
        script.type = 'text/javascript';
        script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js';
        script.async = true;
        script.textContent = JSON.stringify({{
          symbol:                symbol,
          width:                 '100%',
          height:                '100%',
          locale:                'en',
          dateRange:             dateRange,
          colorTheme:            'dark',
          trendLineColor:        'rgba(41,98,255,1)',
          underLineColor:        'rgba(41,98,255,0.15)',
          underLineBottomColor:  'rgba(41,98,255,0)',
          isTransparent:         true,
          autosize:              true,
          largeChartUrl:         ''
        }});
        wrapper.appendChild(script);
        cell.appendChild(wrapper);
      }}

      function switchTF(tf) {{
        document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-' + tf).classList.add('active');
        for (const [groupId, instruments] of Object.entries(GROUPS)) {{
          const grid = document.getElementById('grid-' + groupId);
          const cells = grid.querySelectorAll('.ix-cell');
          instruments.forEach((inst, i) => {{
            if (cells[i]) loadWidget(cells[i], inst.symbol, tf);
          }});
        }}
      }}

      // Build cells once on load, then fill widgets
      for (const [groupId, instruments] of Object.entries(GROUPS)) {{
        const grid = document.getElementById('grid-' + groupId);
        instruments.forEach(inst => {{
          const cell = document.createElement('div');
          cell.className = 'ix-cell';
          grid.appendChild(cell);
        }});
      }}
      switchTF('1D');
    </script>
    """
    return page_wrap('Indexes & ETFs', 'indexes', content)


# ─── Admin Analytics ──────────────────────────────────────────────────────────

@app.route('/admin/analytics')
def admin_analytics():
    if not is_admin():
        return redirect('/')

    s = get_user_stats()
    users = s['users']

    # Build user rows
    user_rows = ''
    for u in users:
        q_color = '#60a5fa' if u['q_count'] > 0 else '#555'
        user_rows += f"""<tr>
          <td style="color:#aaa;font-size:.78rem">{u['id']}</td>
          <td><strong style="color:#e0e0e0">{u['username']}</strong></td>
          <td style="color:#777;font-size:.83rem">{u['email']}</td>
          <td style="color:#aaa;font-size:.83rem">{u['created_date']}</td>
          <td style="color:{q_color};font-weight:700;text-align:center">{u['q_count']}</td>
          <td style="color:#777;font-size:.83rem">{u['last_question']}</td>
        </tr>"""

    content = f"""
    <style>
      .a-table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
      .a-table th {{ text-align:left; padding:9px 12px; color:#555; border-bottom:1px solid #2a2d3e; font-weight:500; }}
      .a-table td {{ padding:9px 12px; border-bottom:1px solid #151820; }}
      .a-table tr:hover td {{ background:#1f2235; }}
    </style>

    <!-- Summary stats -->
    <div class="grid4" style="margin-bottom:24px">
      <div class="card">
        <div class="stat-label">Total Users</div>
        <div class="stat-value">{s['total_users']}</div>
        <div class="stat-sub">registered accounts</div>
      </div>
      <div class="card">
        <div class="stat-label">New This Week</div>
        <div class="stat-value" style="color:#22c55e">{s['new_this_week']}</div>
        <div class="stat-sub">last 7 days</div>
      </div>
      <div class="card">
        <div class="stat-label">Questions Asked</div>
        <div class="stat-value">{s['total_questions']}</div>
        <div class="stat-sub">{s['answered']} answered · {s['pending']} pending</div>
      </div>
      <div class="card">
        <div class="stat-label">Pending Questions</div>
        <div class="stat-value" style="color:{'#f59e0b' if s['pending'] > 0 else '#22c55e'}">{s['pending']}</div>
        <div class="stat-sub"><a href="/ask">Go to Ask Jimmy →</a></div>
      </div>
    </div>

    <!-- User table -->
    <section>
      <h2>Registered Users ({s['total_users']})</h2>
      {'<table class="a-table"><thead><tr><th>#</th><th>Username</th><th>Email</th><th>Joined</th><th style="text-align:center">Questions</th><th>Last Question</th></tr></thead><tbody>' + user_rows + '</tbody></table>' if users else '<p class="note">No users registered yet.</p>'}
    </section>
    """

    return page_wrap('Analytics', 'analytics', content)


if __name__ == '__main__':
    app.run(debug=True)
