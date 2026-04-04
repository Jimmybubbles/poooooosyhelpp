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
from db_efi_scanner import run_efi_scan, load_last_efi_results
from db_wick_scanner import run_wick_scan, load_last_wick_results
from db_picks import (init_tables, get_account, get_positions, get_portfolio_value,
                      get_history, buy_stock, sell_stock, get_daily_changes,
                      get_closed_trades, add_manual_closed_trade, delete_closed_trade, UPLOADS_DIR)
from db_ask import (init_tables as init_ask_tables, register_user, login_user,
                    submit_question, answer_question, get_questions, get_username,
                    get_user_stats)
from db_dividend import (init_tables as init_dividend_tables, get_all_dividend_stocks,
                         get_dividend_stock, upsert_dividend_stock, delete_dividend_stock)
from db_asx import (init_tables as init_asx_tables, ASX_200,
                    get_asx_sparklines_batch, get_asx_latest_prices,
                    get_asx_chart_data, get_tickers_with_data,
                    get_asx_account, get_asx_picks, get_asx_history,
                    get_asx_portfolio_value, buy_asx_stock, sell_asx_stock,
                    get_asx_daily_changes, get_closed_asx_trades,
                    add_manual_closed_asx_trade, delete_closed_asx_trade)
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
    init_dividend_tables()
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

DOW_30 = [
    'AAPL','AMGN','AMZN','AXP','BA','CAT','CRM','CSCO','CVX','DIS',
    'DOW','GS','HD','HON','IBM','JNJ','JPM','KO','MCD','MMM',
    'MRK','MSFT','NKE','NVDA','PG','TRV','UNH','V','VZ','WMT',
]

NASDAQ_100 = [
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO','COST',
    'NFLX','AMD','ADBE','QCOM','TMUS','TXN','AMGN','INTU','INTC','HON',
    'AMAT','CMCSA','BKNG','ISRG','MU','LRCX','PANW','ADI','KLAC','REGN',
    'CRWD','SNPS','CDNS','MELI','ORLY','ABNB','PYPL','CTAS','FTNT','NXPI',
    'MNST','MDLZ','ADP','PAYX','ROST','PCAR','MAR','CPRT','CHTR','MCHP',
    'WDAY','EXC','MRNA','KDP','DLTR','FAST','ODFL','EA','DXCM','CTSH',
    'XEL','BIIB','IDXX','TEAM','ZS','VRTX','ANSS','TTWO','ILMN','GEHC',
    'CEG','FANG','ON','CSGP','ENPH','WBD','LULU','MRVL','DASH','CSX',
    'VRSK','SBUX','ASML','PDD','SIRI','ALGN','SWKS','NTES','SMCI','ARM',
]

SP500_TICKERS = [
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','BRK-B','AVGO',
    'LLY','JPM','UNH','XOM','V','JNJ','MA','PG','HD','COST',
    'MRK','ABBV','CVX','WMT','BAC','KO','MCD','PEP','CSCO','ORCL',
    'ACN','TMO','CRM','WFC','LIN','ABT','AMD','NFLX','DIS','QCOM',
    'TXN','DHR','NKE','PM','INTC','HON','NEE','T','AMGN','UPS',
    'IBM','CAT','SBUX','RTX','GE','SPGI','BMY','LOW','INTU','GS',
    'DE','ELV','AMAT','MS','MMC','MDLZ','GILD','ADP','BKNG','SYK',
    'BLK','CVS','CB','ADI','LRCX','AMT','ISRG','TJX','VRTX','C',
    'REGN','SO','MO','ZTS','PLD','AXP','BSX','MMM','CL','SCHW',
    'DUK','MU','CI','BDX','HCA','EOG','KLAC','PNC','USB','ITW',
    'F','GM','ETN','CME','AON','PSA','FDX','TGT','SHW','NSC',
    'MCO','ECL','MAR','PANW','SNPS','CDNS','CRWD','ORLY','MELI','BA',
    'DELL','HPQ','HPE','PYPL','UBER','COIN','RIVN','SNAP','PINS','RBLX',
    'PLTR','ANET','SMCI','ARM','AXON','DDOG','HUBS','ZM','DOCU','OKTA',
    'SNOW','MDB','CFLT','GTLB','PATH','U','APPN','APPF','PCVX','TMDX',
    'WRB','AFL','MET','PRU','TRV','ALL','AIG','PFG','UNM','CNO',
    'DFS','COF','SYF','ADS','SLM','NAVI','CACC','OMF','ALLY','SOFI',
    'WFC','KEY','RF','FITB','CFG','HBAN','ZION','MTB','CMA','SIVB',
    'WAL','BOKF','WTFC','IBCP','FULT','SNV','GBCI','FBIZ','FFIN','TBBK',
]

def get_perf_data(tickers):
    """
    Returns {ticker: {d1, w1, m1, m3}} % change for each ticker.
    Pulls last 95 days of closes in one query.
    Also returns _error key if something went wrong, and _rows_found count.
    """
    from collections import defaultdict
    result = {t: {'d1': None, 'w1': None, 'm1': None, 'm3': None} for t in tickers}
    result['_error'] = None
    result['_rows_found'] = 0
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

        result['_rows_found'] = len(rows)

        grouped = defaultdict(list)
        for ticker, _, close in rows:
            if close is not None:
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
    except Exception as e:
        result['_error'] = str(e)
    return result


def get_us_sparklines_batch(tickers, bars=60):
    """Return {ticker: [last N closes]} from the prices table."""
    from collections import defaultdict
    result = defaultdict(list)
    if not tickers:
        return result
    try:
        conn = get_connection()
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ticker, close FROM prices
                WHERE ticker IN ({fmt})
                  AND date >= DATE_SUB(CURDATE(), INTERVAL 95 DAY)
                ORDER BY ticker, date ASC
            """, [t.upper() for t in tickers])
            for ticker, close in cur.fetchall():
                if close is not None:
                    result[ticker.upper()].append(float(close))
        conn.close()
        return {t: v[-bars:] for t, v in result.items()}
    except Exception:
        return result


def get_us_latest_prices(tickers):
    """Return {ticker: latest_close} from the prices table."""
    result = {}
    if not tickers:
        return result
    try:
        conn = get_connection()
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT p.ticker, p.close
                FROM prices p
                INNER JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM prices WHERE ticker IN ({fmt})
                    GROUP BY ticker
                ) m ON p.ticker = m.ticker AND p.date = m.max_date
            """, [t.upper() for t in tickers])
            for ticker, close in cur.fetchall():
                result[ticker.upper()] = float(close) if close else None
        conn.close()
    except Exception:
        pass
    return result


def get_us_tickers_with_data(tickers):
    """Return set of tickers from the given list that have data in prices table."""
    if not tickers:
        return set()
    try:
        conn = get_connection()
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT ticker FROM prices WHERE ticker IN ({fmt})",
                        [t.upper() for t in tickers])
            result = {r[0].upper() for r in cur.fetchall()}
        conn.close()
        return result
    except Exception:
        return set()


def get_us_all_tickers_with_data():
    """Return all distinct tickers in the prices table."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")
            result = [r[0].upper() for r in cur.fetchall()]
        conn.close()
        return result
    except Exception:
        return []


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
    admin_lnk = f'<span style="width:1px;background:#2a2d3e;align-self:stretch;margin:0 4px"></span>{lnk("/admin","Admin","admin")}' if is_admin() else ''

    return f"""
    <header>
      <h1>Stock Manager</h1>
      <nav>
        {lnk('/','Dashboard','home')}
        {lnk('/how-it-works','How It Works','howitworks')}
        {lnk('/indexes','Indexes & ETFs','indexes')}
        {lnk('/nasdaq','Nasdaq 100','nasdaq')}
        {lnk('/dow','Dow 30','dow')}
        {lnk('/sp500','S&amp;P 500','sp500')}
        {lnk('/russell','Russell / Small Caps','russell')}
        {lnk('/picks',"Jimmy's Picks",'picks')}
        {lnk('/asx','ASX 200','asx')}
        {lnk('/asx/picks','ASX Picks','asxpicks')}
        {lnk('/dividend','Dividend Picks','dividend')}
        {lnk('/journal','Trade Journal','journal')}
        {lnk('/ask','Ask Jimmy','ask')}
        {admin_lnk}
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

    {f'<div style="text-align:right;margin-top:4px"><a href="/admin" style="font-size:.78rem;color:#555">→ Admin Panel</a></div>' if is_admin() else ''}
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
            cur.execute("SELECT DISTINCT ticker FROM jimmy_picks WHERE status='open'")
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
                pticker = p['ticker']
                action_html = f"""
                <div style="display:flex;gap:8px;align-items:center">
                  <button class="btn btn-amber" style="padding:7px 16px"
                    onclick="openSellModal({p['id']},'{pticker}',{p['shares']},{p['current_price']:.4f},'/picks/sell/{p['id']}')">Sell</button>
                  <a href="/chart/{pticker}" class="btn btn-blue" style="padding:7px 14px;font-size:.82rem">Chart</a>
                </div>"""
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

    sell_modal = """
    <div id="sell-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9000;align-items:center;justify-content:center">
      <div style="background:#13151f;border:1px solid #2a2d3e;border-radius:12px;padding:28px;width:100%;max-width:500px;margin:20px">
        <h3 id="sell-modal-title" style="margin:0 0 20px">Sell Position</h3>
        <form id="sell-form" method="POST" enctype="multipart/form-data">
          <div style="margin-bottom:14px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Sell Price *</label>
            <input id="sell-price-input" name="sell_price" type="number" step="0.0001" required
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div style="margin-bottom:14px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Why I sold</label>
            <textarea name="sell_reason" rows="4" placeholder="Stop loss hit, thesis broke, took profit at target..."
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical"></textarea>
          </div>
          <div style="margin-bottom:20px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Chart Screenshot (sell setup)</label>
            <input name="sell_chart" type="file" accept="image/*" style="color:#aaa;font-size:.85rem">
          </div>
          <div style="display:flex;gap:10px">
            <button type="submit" class="btn btn-amber" style="flex:1">Confirm Sell</button>
            <button type="button" class="btn" style="flex:1;background:#252839" onclick="closeSellModal()">Cancel</button>
          </div>
        </form>
      </div>
    </div>
    <script>
    function openSellModal(pickId, ticker, shares, currentPrice, action) {
      document.getElementById('sell-modal-title').textContent = 'Sell ' + shares + ' shares of ' + ticker;
      document.getElementById('sell-price-input').value = currentPrice;
      document.getElementById('sell-form').action = action;
      document.getElementById('sell-modal').style.display = 'flex';
    }
    function closeSellModal() {
      document.getElementById('sell-modal').style.display = 'none';
    }
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeSellModal();
    });
    </script>"""

    content = err_html + msg_html + summary + add_form + pos_html + hist_html + sell_modal
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
    sell_price  = float(request.form.get('sell_price', 0))
    sell_reason = request.form.get('sell_reason', '').strip()

    sell_image = ''
    file = request.files.get('sell_chart')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        sell_image = f"sell_{pick_id}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, sell_image))

    ok, result = sell_stock(pick_id, sell_price, sell_reason, sell_image)
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
            const barCount = data.ohlcv.length;
            chart.timeScale().setVisibleLogicalRange({ from: 0, to: barCount + Math.round(barCount * 0.9) });
            chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.12, bottom: 0.18 } });
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

    # ── ASX breadth from sparklines ───────────────────────────────────────────
    def asx_breadth(n):
        up = down = flat = 0
        for t in sorted(ASX_200):
            c = sparklines.get(t, [])
            if len(c) > n:
                if   c[-1] > c[-1-n]: up   += 1
                elif c[-1] < c[-1-n]: down += 1
                else:                 flat += 1
        total = up + down + flat
        up_pct   = round(up   / total * 100, 1) if total else 0
        down_pct = round(down / total * 100, 1) if total else 0
        flat_pct = round(100 - up_pct - down_pct, 1)
        return up, down, flat, up_pct, down_pct, flat_pct

    ad_up, ad_dn, ad_fl, ad_up_pct, ad_dn_pct, ad_fl_pct = asx_breadth(1)
    aw_up, aw_dn, aw_fl, aw_up_pct, aw_dn_pct, aw_fl_pct = asx_breadth(5)
    am_up, am_dn, am_fl, am_up_pct, am_dn_pct, am_fl_pct = asx_breadth(21)

    asx_donut_html = ''
    for period, up_pct, dn_pct, fl_pct, up, dn in [
        ('Day',   ad_up_pct, ad_dn_pct, ad_fl_pct, ad_up, ad_dn),
        ('Week',  aw_up_pct, aw_dn_pct, aw_fl_pct, aw_up, aw_dn),
        ('Month', am_up_pct, am_dn_pct, am_fl_pct, am_up, am_dn),
    ]:
        pid = 'asx-' + period.lower()
        cs = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:1.6rem;font-weight:800;color:#fff;white-space:nowrap'
        asx_donut_html += (
            f'<div style="text-align:center">'
            f'<div style="font-size:.82rem;color:#aaa;font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">{period}</div>'
            f'<div style="position:relative;width:150px;height:150px">'
            f'<canvas id="donut-{pid}" width="150" height="150"></canvas>'
            f'<div style="{cs}">{up_pct}%</div>'
            f'</div>'
            f'<div style="font-size:.88rem;margin-top:10px;font-weight:600">'
            f'<span style="color:#22c55e">&#9650; {up} up</span>'
            f'<span style="color:#555;margin:0 8px">/</span>'
            f'<span style="color:#ef4444">&#9660; {dn} down</span>'
            f'</div></div>'
        )

    # Updated rows with bigger fonts + day %
    rows_html2 = ''
    for ticker in sorted(ASX_200):
        closes  = sparklines.get(ticker, [])
        price   = latest.get(ticker)
        svg2    = sparkline_svg(closes)
        price_s = f'A${price:.3f}' if price else '—'
        has_row = ticker in with_data
        day_chg = ''
        if len(closes) >= 2:
            pct = (closes[-1] - closes[-2]) / closes[-2] * 100
            col = '#22c55e' if pct >= 0 else '#ef4444'
            day_chg = f'<span style="color:{col};font-size:.95rem;font-weight:600">{"+" if pct>=0 else ""}{pct:.2f}%</span>'
        rows_html2 += f"""
        <tr class="asx-row" data-ticker="{ticker}" style="cursor:{'pointer' if has_row else 'default'}">
          <td>
            <div style="display:flex;align-items:center;gap:12px">
              <strong style="color:#60a5fa;min-width:68px;font-size:1rem">{ticker}</strong>
              {svg2 if has_row else ''}
            </div>
          </td>
          <td style="font-weight:700;color:#fff;font-size:1rem">{price_s}</td>
          <td style="font-size:.95rem;font-weight:600">{day_chg}</td>
        </tr>"""

    content = f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>

    <!-- Dashboard header -->
    <section style="margin-bottom:20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <span></span>
        <div class="btn-row">{dl_btn}</div>
      </div>

      <!-- STW area chart -->
      <div style="margin-bottom:18px">
        <div style="font-size:.78rem;color:#888;font-weight:600;margin-bottom:8px">
          STW &nbsp;<span style="color:#555;font-weight:400">— ASX 200 ETF · 60 Day</span>
        </div>
        <div id="asx-etf-area" style="height:220px;background:#0a0c14;border-radius:8px"></div>
      </div>

      <!-- Breadth donuts -->
      <div>
        <p style="font-size:.88rem;color:#888;margin-bottom:14px">
          Percentage of <strong style="color:#fff">ASX 200</strong> stocks moving up or down over each time period
        </p>
        <div style="display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap">
          {asx_donut_html}
        </div>
      </div>

      <div style="margin-top:14px;font-size:.8rem;color:#444">
        {len(with_data)} tickers with data &nbsp;·&nbsp; click any row to expand chart
      </div>
    </section>

    <script>
    // ASX ETF chart
    (function(){{
      fetch('/api/asx-chart/STW')
        .then(r=>r.json())
        .then(data=>{{
          if(data.error||!data.ohlcv) return;
          const recent = data.ohlcv.slice(-60);
          const chart = LightweightCharts.createChart(document.getElementById('asx-etf-area'),{{
            layout:{{background:{{color:'#0a0c14'}},textColor:'#555'}},
            grid:{{vertLines:{{color:'#12141e'}},horzLines:{{color:'#12141e'}}}},
            rightPriceScale:{{borderColor:'#1a1d2e'}},
            timeScale:{{borderColor:'#1a1d2e',timeVisible:false}},
            crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
            handleScroll:false, handleScale:false,
          }});
          const area = chart.addAreaSeries({{
            lineColor:'#22c55e', topColor:'#22c55e44',
            bottomColor:'#22c55e00', lineWidth:2,
          }});
          area.setData(recent.map(b=>({{time:b.time,value:b.close}})));
          chart.timeScale().fitContent();
        }}).catch(()=>{{}});
    }})();
    // Breadth donuts
    (function(){{
      const donuts = [
        {{ id:'donut-asx-day',   up:{ad_up_pct}, dn:{ad_dn_pct}, fl:{ad_fl_pct} }},
        {{ id:'donut-asx-week',  up:{aw_up_pct}, dn:{aw_dn_pct}, fl:{aw_fl_pct} }},
        {{ id:'donut-asx-month', up:{am_up_pct}, dn:{am_dn_pct}, fl:{am_fl_pct} }},
      ];
      donuts.forEach(d => {{
        const ctx = document.getElementById(d.id).getContext('2d');
        new Chart(ctx, {{
          type: 'doughnut',
          data: {{ datasets: [{{ data:[d.up,d.dn,d.fl],
            backgroundColor:['#22c55e','#ef4444','#1f2235'], borderWidth:0, hoverOffset:4 }}] }},
          options: {{
            cutout:'70%',
            animation:{{ animateRotate:true, duration:1200, easing:'easeInOutQuart' }},
            plugins:{{ legend:{{display:false}},
              tooltip:{{ callbacks:{{ label: ctx=>['Up','Down','Flat'][ctx.dataIndex]+': '+ctx.parsed+'%' }} }} }}
          }}
        }});
      }});
    }})();
    </script>

    {log_section}
    <section>
      <style>
        .asx-table {{ width:100%; border-collapse:collapse; font-size:.95rem; }}
        .asx-table th {{ text-align:left; padding:10px 14px; color:#777;
                        border-bottom:1px solid #2a2d3e; font-weight:500; cursor:pointer; user-select:none; font-size:.82rem; }}
        .asx-table th:hover {{ color:#aaa; }}
        .asx-table th.sort-asc::after  {{ content:' ▲'; font-size:.65rem; color:#60a5fa; }}
        .asx-table th.sort-desc::after {{ content:' ▼'; font-size:.65rem; color:#60a5fa; }}
        .asx-table td {{ padding:10px 14px; border-bottom:1px solid #151820; vertical-align:middle; }}
        .asx-table .asx-row:hover td {{ background:#1f2235; }}
        .asx-table .asx-row.active td {{ background:#1a2235; }}
        .asx-drop td {{ padding:0 !important; }}
      </style>
      <table class="asx-table">
        <thead><tr>
          <th onclick="sortAsx(this)">Ticker</th>
          <th onclick="sortAsx(this)">Price (AUD)</th>
          <th onclick="sortAsx(this)">Day %</th>
        </tr></thead>
        <tbody id="asx-tbody">{rows_html2}</tbody>
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
        const an = parseFloat(av.replace('A$','').replace('%','')), bn = parseFloat(bv.replace('A$','').replace('%',''));
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


@app.route('/api/us-chart/<ticker>')
def us_chart_api(ticker):
    ticker = ticker.upper()
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM prices WHERE ticker = %s ORDER BY date ASC
            """, (ticker,))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)})

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
                pticker = p['ticker']
                action_html = f"""
                <div style="display:flex;gap:8px;align-items:center">
                  <button class="btn btn-amber" style="padding:7px 16px"
                    onclick="openSellModal({p['id']},'{pticker}',{p['shares']},{p['current_price']:.4f},'/asx/picks/sell/{p['id']}')">Sell</button>
                </div>"""
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

    sell_modal = """
    <div id="sell-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9000;align-items:center;justify-content:center">
      <div style="background:#13151f;border:1px solid #2a2d3e;border-radius:12px;padding:28px;width:100%;max-width:500px;margin:20px">
        <h3 id="sell-modal-title" style="margin:0 0 20px">Sell Position</h3>
        <form id="sell-form" method="POST" enctype="multipart/form-data">
          <div style="margin-bottom:14px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Sell Price *</label>
            <input id="sell-price-input" name="sell_price" type="number" step="0.0001" required
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div style="margin-bottom:14px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Why I sold</label>
            <textarea name="sell_reason" rows="4" placeholder="Stop loss hit, thesis broke, took profit at target..."
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical"></textarea>
          </div>
          <div style="margin-bottom:20px">
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Chart Screenshot (sell setup)</label>
            <input name="sell_chart" type="file" accept="image/*" style="color:#aaa;font-size:.85rem">
          </div>
          <div style="display:flex;gap:10px">
            <button type="submit" class="btn btn-amber" style="flex:1">Confirm Sell</button>
            <button type="button" class="btn" style="flex:1;background:#252839" onclick="closeSellModal()">Cancel</button>
          </div>
        </form>
      </div>
    </div>
    <script>
    function openSellModal(pickId, ticker, shares, currentPrice, action) {
      document.getElementById('sell-modal-title').textContent = 'Sell ' + shares + ' shares of ' + ticker;
      document.getElementById('sell-price-input').value = currentPrice;
      document.getElementById('sell-form').action = action;
      document.getElementById('sell-modal').style.display = 'flex';
    }
    function closeSellModal() {
      document.getElementById('sell-modal').style.display = 'none';
    }
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeSellModal();
    });
    </script>"""

    msg = request.args.get('msg', '')
    msg_html = f'<div style="background:#1a2e1a;border:1px solid #22c55e;border-radius:8px;padding:12px 16px;margin-bottom:20px;color:#86efac">{msg}</div>' if msg else ''
    err = request.args.get('err', '')
    err_html = f'<div class="err-box">{err}</div>' if err else ''

    content = err_html + msg_html + summary + add_form + pos_html + hist_html + sell_modal
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
    sell_price  = float(request.form.get('sell_price', 0))
    sell_reason = request.form.get('sell_reason', '').strip()

    sell_image = ''
    file = request.files.get('sell_chart')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        sell_image = f"sell_{pick_id}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, sell_image))

    ok, result = sell_asx_stock(pick_id, sell_price, sell_reason, sell_image)
    if ok:
        sign = '+' if result >= 0 else ''
        return redirect(f'/asx/picks?msg=Sold+position+P%26L+{sign}A${result:.2f}')
    return redirect(f'/asx/picks?err={result}')


# ─── Trade Journal ────────────────────────────────────────────────────────────

@app.route('/journal')
def journal_page():
    msg = request.args.get('msg', '')
    err = request.args.get('err', '')
    msg_html = f'<div style="background:#1a2e1a;border:1px solid #22c55e;border-radius:8px;padding:12px 16px;margin-bottom:20px;color:#86efac">{msg}</div>' if msg else ''
    err_html = f'<div class="err-box">{err}</div>' if err else ''

    us_trades  = get_closed_trades()
    asx_trades = get_closed_asx_trades()
    all_trades = us_trades + asx_trades
    all_trades.sort(key=lambda t: t['sell_date'], reverse=True)

    total   = len(all_trades)
    wins    = sum(1 for t in all_trades if t['pnl'] >= 0)
    losses  = total - wins
    total_pnl = sum(t['pnl'] for t in all_trades)
    win_rate  = (wins / total * 100) if total else 0
    pnl_color = '#22c55e' if total_pnl >= 0 else '#ef4444'
    pnl_sign  = '+' if total_pnl >= 0 else ''

    stats = f"""
    <div class="grid4" style="margin-bottom:28px">
      <div class="card">
        <div class="stat-label">Closed Trades</div>
        <div class="stat-value">{total}</div>
      </div>
      <div class="card">
        <div class="stat-label">Win Rate</div>
        <div class="stat-value" style="color:{'#22c55e' if win_rate>=50 else '#ef4444'}">{win_rate:.0f}%</div>
        <div class="stat-sub">{wins}W / {losses}L</div>
      </div>
      <div class="card">
        <div class="stat-label">Total Realised P&amp;L</div>
        <div class="stat-value" style="color:{pnl_color}">{pnl_sign}${total_pnl:,.2f}</div>
      </div>
      <div class="card">
        <div class="stat-label">Avg P&amp;L per Trade</div>
        <div class="stat-value" style="color:{pnl_color}">{pnl_sign}${(total_pnl/total):,.2f}</div>
      </div>
    </div>""" if total else ''

    cards = ''
    for t in all_trades:
        pnl_c = '#22c55e' if t['pnl'] >= 0 else '#ef4444'
        sign  = '+' if t['pnl'] >= 0 else ''
        market_badge = f'<span style="font-size:.72rem;padding:2px 8px;border-radius:4px;background:#1e3a5f;color:#60a5fa;font-weight:600">{t["market"]}</span>'

        buy_img_html = ''
        if t['buy_image']:
            buy_img_html = f'<img src="/picks/image/{t["buy_image"]}" onclick="openLightbox(this.src)" style="width:100%;border-radius:6px;margin-bottom:8px;border:1px solid #2a2d3e;cursor:pointer">'

        sell_img_html = ''
        if t['sell_image']:
            sell_img_html = f'<img src="/picks/image/{t["sell_image"]}" onclick="openLightbox(this.src)" style="width:100%;border-radius:6px;margin-bottom:8px;border:1px solid #2a2d3e;cursor:pointer">'

        buy_reason_html  = f'<p style="color:#aaa;font-size:.83rem;line-height:1.5;margin:0">{t["buy_reason"]}</p>'  if t['buy_reason']  else ''
        sell_reason_html = f'<p style="color:#aaa;font-size:.83rem;line-height:1.5;margin:0">{t["sell_reason"]}</p>' if t['sell_reason'] else ''
        tid = t['id']
        tmkt = t['market']
        delete_btn = f'<form method="POST" action="/journal/delete/{tid}/{tmkt}" onsubmit="return confirm(\'Delete this trade?\')"><button type="submit" style="font-size:.75rem;padding:4px 12px;background:transparent;border:1px solid #3a2020;border-radius:5px;color:#666;cursor:pointer">Delete</button></form>' if is_admin() else ''

        cards += f"""
        <div class="card" style="margin-bottom:20px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:10px">
              <span style="font-size:1.3rem;font-weight:700;color:#60a5fa">{t['ticker']}</span>
              {market_badge}
            </div>
            <span style="font-size:1.1rem;font-weight:700;color:{pnl_c}">{sign}${t['pnl']:,.2f} ({sign}{t['pnl_pct']:.1f}%)</span>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:16px;font-size:.83rem">
            <div><span style="color:#555">Bought</span><br><strong>{t['bought_date']}</strong></div>
            <div><span style="color:#555">Sold</span><br><strong>{t['sell_date']}</strong></div>
            <div><span style="color:#555">Buy Price</span><br><strong>${t['buy_price']:.4f}</strong></div>
            <div><span style="color:#555">Sell Price</span><br><strong>${t['sell_price']:.4f}</strong></div>
            <div><span style="color:#555">Shares</span><br><strong>{t['shares']:,.2f}</strong></div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px">
            <div>
              <div style="font-size:.72rem;color:#555;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Buy Setup</div>
              {buy_img_html}
              {buy_reason_html}
            </div>
            <div>
              <div style="font-size:.72rem;color:#555;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Sell Setup</div>
              {sell_img_html}
              {sell_reason_html}
            </div>
          </div>
          {delete_btn}
        </div>"""

    if not all_trades:
        cards = '<p class="note">No closed trades yet. Sell a position from Jimmy\'s Picks or ASX Picks to start your journal.</p>'

    lightbox = """
    <div id="lightbox" onclick="closeLightbox()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9999;align-items:center;justify-content:center;cursor:zoom-out">
      <img id="lightbox-img" style="max-width:92vw;max-height:92vh;border-radius:8px;box-shadow:0 0 60px rgba(0,0,0,.8)">
    </div>
    <script>
    function openLightbox(src){document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').style.display='flex';}
    function closeLightbox(){document.getElementById('lightbox').style.display='none';}
    document.addEventListener('keydown',function(e){if(e.key==='Escape')closeLightbox();});
    </script>"""

    add_form = '' if not is_admin() else """
    <section>
      <h2>Add Closed Trade</h2>
      <form method="POST" action="/journal/add" enctype="multipart/form-data">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:14px">
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Market *</label>
            <select name="market" style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
              <option value="US">US</option>
              <option value="ASX">ASX</option>
            </select>
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Ticker *</label>
            <input name="ticker" placeholder="e.g. AAPL" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Shares *</label>
            <input name="shares" type="number" step="0.0001" placeholder="e.g. 100" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Buy Price *</label>
            <input name="buy_price" type="number" step="0.0001" placeholder="e.g. 150.00" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Buy Date *</label>
            <input name="buy_date" type="date" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Sell Price *</label>
            <input name="sell_price" type="number" step="0.0001" placeholder="e.g. 180.00" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Sell Date *</label>
            <input name="sell_date" type="date" required style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.9rem">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px">
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Why I bought</label>
            <textarea name="buy_reason" rows="3" placeholder="Channel forming, EMA squeeze..."
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical"></textarea>
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Why I sold</label>
            <textarea name="sell_reason" rows="3" placeholder="Stop loss hit, took profit..."
              style="width:100%;padding:8px 10px;background:#0a0c14;border:1px solid #2a2d3e;border-radius:6px;color:#fff;font-size:.88rem;resize:vertical"></textarea>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px">
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Buy Chart</label>
            <input name="buy_chart" type="file" accept="image/*" style="color:#aaa;font-size:.85rem">
          </div>
          <div>
            <label style="font-size:.78rem;color:#666;display:block;margin-bottom:4px">Sell Chart</label>
            <input name="sell_chart" type="file" accept="image/*" style="color:#aaa;font-size:.85rem">
          </div>
        </div>
        <button type="submit" class="btn btn-green">+ Add to Journal</button>
      </form>
    </section>"""

    content = f"""
    {err_html}{msg_html}
    {add_form}
    <section>
      <h2>Closed Trades</h2>
      <p style="color:#555;font-size:.88rem;margin-bottom:24px">Every closed trade — the good and the bad. Honesty builds trust.</p>
      {stats}
      {cards}
    </section>
    {lightbox}"""

    return page_wrap('Trade Journal', 'journal', content)


@app.route('/journal/add', methods=['POST'])
def journal_add():
    if not is_admin():
        return redirect('/journal')

    market     = request.form.get('market', 'US')
    ticker     = request.form.get('ticker', '').strip().upper()
    shares     = request.form.get('shares', '0')
    buy_price  = request.form.get('buy_price', '0')
    buy_date   = request.form.get('buy_date', '')
    buy_reason = request.form.get('buy_reason', '').strip()
    sell_price = request.form.get('sell_price', '0')
    sell_date  = request.form.get('sell_date', '')
    sell_reason = request.form.get('sell_reason', '').strip()

    buy_image = ''
    file = request.files.get('buy_chart')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        buy_image = f"buy_{ticker}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, buy_image))

    sell_image = ''
    file = request.files.get('sell_chart')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        sell_image = f"sell_{ticker}_{uuid.uuid4().hex[:8]}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, sell_image))

    if market == 'ASX':
        ok, result = add_manual_closed_asx_trade(
            ticker, shares, buy_price, buy_date, buy_reason, buy_image,
            sell_price, sell_date, sell_reason, sell_image)
    else:
        ok, result = add_manual_closed_trade(
            ticker, shares, buy_price, buy_date, buy_reason, buy_image,
            sell_price, sell_date, sell_reason, sell_image)

    if ok:
        sign = '+' if result >= 0 else ''
        return redirect(f'/journal?msg={ticker}+added+to+journal.+P%26L:+{sign}${result:.2f}')
    return redirect(f'/journal?err={result}')


@app.route('/journal/delete/<int:pick_id>/<market>', methods=['POST'])
def journal_delete(pick_id, market):
    if not is_admin():
        return redirect('/journal')
    if market == 'ASX':
        delete_closed_asx_trade(pick_id)
    else:
        delete_closed_trade(pick_id)
    return redirect('/journal?msg=Trade+deleted')


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


# ─── Wick Scanner ─────────────────────────────────────────────────────────────

def _run_wick_scan_job():
    global _job_running, _job_name
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Wick Scan ===\nStarted: {datetime.now()}\n\n")
    try:
        run_wick_scan(log_callback=lambda m: open(LOG_FILE, 'a').write(m))
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nERROR: {e}\n")
    finally:
        with _job_lock:
            _job_running = False
            _job_name    = ''


def start_wick_scan():
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            return False
        _job_running = True
        _job_name    = 'Wick Scan'
    threading.Thread(target=_run_wick_scan_job, daemon=True).start()
    return True


@app.route('/run-wick')
def run_wick():
    if not is_admin():
        return redirect('/admin')
    start_wick_scan()
    return redirect('/wick')


@app.route('/wick')
def wick_page():
    if not is_admin():
        return redirect('/')

    with _job_lock:
        running = _job_running
        jname   = _job_name

    last = load_last_wick_results()

    if running and jname == 'Wick Scan':
        run_btn = '<span class="btn btn-off">⏳ Scanning…</span>'
    elif running:
        run_btn = '<span class="btn btn-off">Another job running</span>'
    else:
        run_btn = '<a href="/run-wick" class="btn btn-blue">▶ Run Wick Scan</a>'

    def score_color(s):
        if s >= 8:  return '#22c55e'
        if s >= 5:  return '#f59e0b'
        return '#555'

    rows_html = ''
    if last and last.get('results'):
        for r in last['results']:
            sc   = r['score']
            gc   = '#22c55e' if r['gain_pct'] >= 0 else '#ef4444'
            gs   = '+' if r['gain_pct'] >= 0 else ''
            held = r['weeks_held']
            rows_html += f"""
            <tr class="wick-row" data-ticker="{r['ticker']}" data-wick-date="{r['wick_date']}">
              <td><strong style="color:#60a5fa;font-size:1rem">{r['ticker']}</strong></td>
              <td style="color:#aaa">{r['wick_date']}</td>
              <td style="text-align:center">
                <span style="background:{score_color(sc)};color:#fff;padding:3px 10px;
                             border-radius:12px;font-weight:700;font-size:.85rem">{sc}</span>
              </td>
              <td style="color:#fff;font-weight:600">{r['wick_ratio']}×</td>
              <td style="color:#aaa">{held}w</td>
              <td style="color:#888">{r['close_pct']}%</td>
              <td style="color:#fff;font-weight:600">${r['current_price']:,.4f}</td>
              <td style="color:{gc};font-weight:700">{gs}{r['gain_pct']:.2f}%</td>
            </tr>"""

    scan_info = ''
    if last:
        scan_info = (f"Last scan: {last['scan_date']} &nbsp;·&nbsp; "
                     f"{last['total']} signals from {last['tickers_scanned']} tickers")

    chart_js = """
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    // LightweightCharts v4 series primitive — paneViews() → renderer() → draw()
    class VerticalLineRenderer {
      constructor(time, color, chart) {
        this._time = time; this._color = color; this._chart = chart;
      }
      draw(target) {
        const x = this._chart.timeScale().timeToCoordinate(this._time);
        if (x === null) return;
        target.useBitmapCoordinateSpace(scope => {
          const ctx = scope.context;
          const xb = Math.round(x * scope.horizontalPixelRatio);
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(xb, 0);
          ctx.lineTo(xb, scope.bitmapSize.height);
          ctx.strokeStyle = this._color;
          ctx.lineWidth = Math.round(2 * scope.horizontalPixelRatio);
          ctx.setLineDash([6, 4]);
          ctx.stroke();
          ctx.restore();
        });
      }
    }
    class VerticalLinePaneView {
      constructor(time, color, chart) {
        this._renderer = new VerticalLineRenderer(time, color, chart);
      }
      renderer() { return this._renderer; }
      zOrder()   { return 'normal'; }
    }
    class VerticalLine {
      constructor(time, color = '#ef4444') {
        this._time = time; this._color = color;
        this._chart = null; this._views = [];
      }
      attached({ chart }) {
        this._chart = chart;
        this._views = [new VerticalLinePaneView(this._time, this._color, chart)];
      }
      detached()       { this._views = []; }
      paneViews()      { return this._views; }
      updateAllViews() {}
    }

    document.querySelectorAll('.wick-row').forEach(row => {
      row.addEventListener('click', () => {
        const ticker   = row.dataset.ticker;
        const wickDate = row.dataset.wickDate;
        const existId  = 'wdrop-' + ticker;
        const exist = document.getElementById(existId);
        if (exist) { exist.remove(); row.classList.remove('active'); return; }
        document.querySelectorAll('.wick-drop').forEach(d => d.remove());
        document.querySelectorAll('.wick-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        const drop = document.createElement('tr');
        drop.id = existId; drop.className = 'wick-drop';
        drop.innerHTML = `<td colspan="8" style="background:#080a10;padding:16px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <span style="color:#fff;font-weight:700;font-size:1rem">${ticker}</span>
            <span style="color:#555;font-size:.75rem" id="ws-${ticker}">Loading...</span>
          </div>
          <div id="wm-${ticker}" style="height:420px;background:#0a0c14;border-radius:6px"></div>
          <div id="wv-${ticker}" style="height:65px;background:#0a0c14;border-radius:6px;margin-top:3px"></div>
        </td>`;
        row.parentNode.insertBefore(drop, row.nextSibling);
        fetch('/api/us-chart/' + ticker)
          .then(r => r.json())
          .then(data => {
            if (data.error) { document.getElementById('ws-' + ticker).textContent = data.error; return; }
            document.getElementById('ws-' + ticker).textContent = data.bars + ' bars · ' + data.date_range;
            const chart = LightweightCharts.createChart(document.getElementById('wm-' + ticker), {
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
            // Find closest actual trading day in the data to the wick date
            // (weekly wick date is a Friday that may not be in the daily series)
            const wickMs = new Date(wickDate).getTime();
            let snapDate = wickDate;
            let minDiff = Infinity;
            for (const bar of data.ohlcv) {
              const diff = Math.abs(new Date(bar.time).getTime() - wickMs);
              if (diff < minDiff) { minDiff = diff; snapDate = bar.time; }
            }
            candles.attachPrimitive(new VerticalLine(snapDate));
            const ema5  = chart.addLineSeries({ color: '#60a5fa', lineWidth: 1, title: 'EMA5' });
            const ema26 = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'EMA26' });
            ema5.setData(data.ema5); ema26.setData(data.ema26);
            const barCount = data.ohlcv.length;
            chart.timeScale().setVisibleLogicalRange({ from: 0, to: barCount + Math.round(barCount * 0.9) });
            chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.12, bottom: 0.18 } });
            const vc = LightweightCharts.createChart(document.getElementById('wv-' + ticker), {
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
          .catch(e => { document.getElementById('ws-' + ticker).textContent = 'Failed: ' + e; });
      });
    });
    </script>"""

    content = f"""
    <section style="margin-bottom:20px">
      <h2>Weekly Wick Scanner</h2>
      <p style="font-size:.88rem;color:#888;margin-bottom:16px">
        Finds weekly candles with a long lower wick (2×+ body) that have closed in the
        top 30% of range — and scores them by how many subsequent weeks have held above
        the wick low. Higher score = stronger signal.
      </p>
      <div class="btn-row" style="margin-bottom:8px">{run_btn}</div>
      <p class="note">{scan_info}</p>
    </section>

    {'<section><h2>Log</h2><pre>' + get_log().replace("<","&lt;") + '</pre></section>' if running and jname == "Wick Scan" else ''}

    <section>
      <style>
        .wick-table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
        .wick-table th {{ text-align:left; padding:10px 14px; color:#777; font-size:.78rem;
                         border-bottom:1px solid #2a2d3e; font-weight:500;
                         cursor:pointer; user-select:none; }}
        .wick-table th:hover {{ color:#aaa; }}
        .wick-table th.sort-asc::after  {{ content:' ▲'; font-size:.6rem; color:#60a5fa; }}
        .wick-table th.sort-desc::after {{ content:' ▼'; font-size:.6rem; color:#60a5fa; }}
        .wick-table td {{ padding:10px 14px; border-bottom:1px solid #151820; vertical-align:middle; }}
        .wick-table .wick-row:hover td {{ background:#1f2235; cursor:pointer; }}
        .wick-table .wick-row.active td {{ background:#1a2235; }}
        .wick-drop td {{ padding:0 !important; }}
        .wick-filter-btn {{ background:#1a1d2e; border:1px solid #2a2d3e; color:#888;
                            padding:6px 16px; border-radius:6px; cursor:pointer; font-size:.82rem; }}
        .wick-filter-btn.active {{ background:#1e3a5f; border-color:#3b82f6; color:#60a5fa; font-weight:600; }}
      </style>

      <div style="background:#0d0f1a;border:1px solid #1e2235;border-radius:8px;padding:14px 16px;margin-bottom:16px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <span style="color:#aaa;font-size:.82rem;font-weight:600;letter-spacing:.04em">TRADINGVIEW WATCHLIST</span>
          <button onclick="copyTVList()" id="tv-copy-btn"
            style="background:#1e3a5f;border:1px solid #3b82f6;color:#60a5fa;padding:5px 14px;
                   border-radius:5px;cursor:pointer;font-size:.78rem;font-weight:600">
            Copy
          </button>
        </div>
        <textarea id="tv-list" readonly rows="3"
          style="width:100%;background:#080a10;border:1px solid #1a1d2e;border-radius:5px;
                 color:#c7d2fe;font-size:.8rem;padding:8px 10px;resize:vertical;
                 font-family:monospace;box-sizing:border-box;line-height:1.6"></textarea>
        <p style="color:#444;font-size:.72rem;margin:6px 0 0">
          Paste directly into TradingView → Watchlist → Import. Updates when you switch Last Week / All.
        </p>
      </div>

      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <button class="wick-filter-btn active" id="wf-week" onclick="setWickFilter('week')">Last Week</button>
        <button class="wick-filter-btn"         id="wf-all"  onclick="setWickFilter('all')">All Signals</button>
        <span id="wick-count" style="color:#555;font-size:.78rem;margin-left:4px"></span>
      </div>
      <table class="wick-table">
        <thead><tr>
          <th onclick="sortWick(this)">Ticker</th>
          <th onclick="sortWick(this)">Wick Date</th>
          <th onclick="sortWick(this)" style="text-align:center">Score</th>
          <th onclick="sortWick(this)">Wick ×</th>
          <th onclick="sortWick(this)">Held</th>
          <th onclick="sortWick(this)">Close %</th>
          <th onclick="sortWick(this)">Current</th>
          <th onclick="sortWick(this)">Gain</th>
        </tr></thead>
        <tbody id="wick-tbody">
          {rows_html if rows_html else '<tr><td colspan="8" style="color:#555;padding:20px">No results yet — run the scan.</td></tr>'}
        </tbody>
      </table>
    </section>
    <script>
    function sortWick(th) {{
      const tbody = document.getElementById('wick-tbody');
      const idx = th.cellIndex;
      const asc = th.classList.contains('sort-desc');
      th.closest('thead').querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      const rows = Array.from(tbody.querySelectorAll('.wick-row'));
      rows.sort((a, b) => {{
        const av = a.cells[idx].textContent.trim();
        const bv = b.cells[idx].textContent.trim();
        const an = parseFloat(av.replace(/[^0-9.-]/g,'')), bn = parseFloat(bv.replace(/[^0-9.-]/g,''));
        const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
        return asc ? cmp : -cmp;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }}

    // Find the most recent wick date across all rows
    function getMostRecentWickDate() {{
      let latest = '';
      document.querySelectorAll('.wick-row').forEach(r => {{
        const d = r.dataset.wickDate || '';
        if (d > latest) latest = d;
      }});
      return latest;
    }}

    function setWickFilter(mode) {{
      document.getElementById('wf-week').classList.toggle('active', mode === 'week');
      document.getElementById('wf-all').classList.toggle('active',  mode === 'all');
      const latestDate = getMostRecentWickDate();
      let visible = 0;
      document.querySelectorAll('.wick-row').forEach(r => {{
        const show = (mode === 'all') || (r.dataset.wickDate === latestDate);
        r.style.display = show ? '' : 'none';
        if (show) visible++;
        // close any open drop if its row is hidden
        if (!show) {{
          const drop = document.getElementById('wdrop-' + r.dataset.ticker);
          if (drop) {{ drop.remove(); r.classList.remove('active'); }}
        }}
      }});
      document.getElementById('wick-count').textContent = visible + ' signal' + (visible !== 1 ? 's' : '');
      updateTVList();
    }}

    function updateTVList() {{
      const tickers = [];
      document.querySelectorAll('.wick-row').forEach(r => {{
        if (r.style.display !== 'none') tickers.push(r.dataset.ticker);
      }});
      document.getElementById('tv-list').value = tickers.join(',');
    }}

    function copyTVList() {{
      const ta = document.getElementById('tv-list');
      ta.select();
      ta.setSelectionRange(0, 99999);
      navigator.clipboard.writeText(ta.value).then(() => {{
        const btn = document.getElementById('tv-copy-btn');
        btn.textContent = 'Copied!';
        btn.style.background = '#14532d';
        btn.style.borderColor = '#22c55e';
        btn.style.color = '#4ade80';
        setTimeout(() => {{
          btn.textContent = 'Copy';
          btn.style.background = '#1e3a5f';
          btn.style.borderColor = '#3b82f6';
          btn.style.color = '#60a5fa';
        }}, 2000);
      }});
    }}

    // Default to last-week view on load
    setWickFilter('week');
    </script>
    {chart_js}"""

    return page_wrap('Wick Scanner', 'wick', content, auto_refresh=(running and jname == 'Wick Scan'))


# ─── EFI Scanner ──────────────────────────────────────────────────────────────

def _run_efi_scan_job():
    global _job_running, _job_name
    def log(msg):
        with open(LOG_FILE, 'a') as f:
            f.write(msg)
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== EFI Scan ===\nStarted: {datetime.now()}\n\n")
    try:
        run_efi_scan(log_callback=log)
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f"\nFATAL ERROR: {e}\n")
    finally:
        _job_running = False
        _job_name    = None


def start_efi_scan():
    global _job_running, _job_name
    if _job_running:
        return
    _job_running = True
    _job_name    = 'EFI Scan'
    import threading
    threading.Thread(target=_run_efi_scan_job, daemon=True).start()


@app.route('/efi')
def efi_page():
    running = _job_running and _job_name == 'EFI Scan'
    data    = load_last_efi_results()

    fi_color_map = {
        'maroon': ('#7f1d1d', '#fca5a5'),
        'orange': ('#78350f', '#fcd34d'),
        'lime':   ('#14532d', '#86efac'),
        'teal':   ('#134e4a', '#5eead4'),
    }

    table = ''
    if data and data.get('results'):
        rows = ''
        for r in data['results']:
            color, tc = fi_color_map.get(r['fi_color'], ('#1e2130', '#888'))
            rows += f"""<tr style="border-bottom:1px solid #151820">
              <td style="padding:9px 14px;font-weight:700">{r['ticker']}</td>
              <td style="padding:9px 10px;color:#aaa">${r['price']:,.2f}</td>
              <td style="padding:9px 10px;color:#22c55e">{r['norm_price']:+.4f}</td>
              <td style="padding:9px 10px;color:#f87171">{r['histogram']:+.4f}</td>
              <td style="padding:9px 10px;background:{color};color:{tc};text-align:center;font-size:.78rem;font-weight:700">{r['fi_color']}</td>
            </tr>"""
        scan_date = data.get('scan_date', '')
        table = f"""
        <p style="color:#555;font-size:.8rem;margin-bottom:10px">Last scan: {scan_date} — {data['total']} setups</p>
        <div class="card" style="padding:0;overflow:hidden">
          <table style="width:100%;border-collapse:collapse;font-size:.84rem">
            <thead>
              <tr style="border-bottom:2px solid #2a2d3e">
                <th style="text-align:left;padding:9px 14px;color:#555;font-weight:500">Ticker</th>
                <th style="text-align:left;padding:9px 10px;color:#555;font-weight:500">Price</th>
                <th style="text-align:left;padding:9px 10px;color:#555;font-weight:500">Norm Price</th>
                <th style="text-align:left;padding:9px 10px;color:#555;font-weight:500">Histogram</th>
                <th style="text-align:center;padding:9px 10px;color:#555;font-weight:500">FI Color</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    if running:
        log_content = ''
        try:
            with open(LOG_FILE) as f:
                log_content = f.read()
        except Exception:
            pass
        run_btn = '<span class="btn" style="background:#1e2130;color:#555;cursor:not-allowed">⏳ Scanning...</span>'
        matrix_log = f'<pre style="background:#0a0c12;color:#00ff41;padding:16px;border-radius:8px;font-size:.72rem;max-height:300px;overflow-y:auto;margin-top:16px;font-family:monospace">{log_content}</pre>'
    else:
        run_btn    = '<a href="/run-efi" class="btn btn-blue">▶ Run EFI Scan</a>' if is_admin() else ''
        matrix_log = ''

    content = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <div>
        <h2 style="margin:0">EFI Scanner</h2>
        <p style="color:#666;font-size:.83rem;margin:4px 0 0">
          Channel printing + Normalized price &gt; 0 + Histogram &lt; 0 — pullback in trend setup
        </p>
      </div>
      {run_btn}
    </div>
    {matrix_log}
    {table if table else '<p class="note">No scan run yet. Click Run EFI Scan above.</p>'}
    """
    return page_wrap('EFI Scan', 'efi', content, auto_refresh=running)


@app.route('/run-efi')
def run_efi_route():
    if not is_admin():
        return redirect('/efi')
    start_efi_scan()
    return redirect('/efi')


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

    debug_bar = ''
    if perf.get('_error'):
        debug_bar = f'<div style="background:#7f1d1d;color:#fca5a5;padding:10px 16px;border-radius:6px;margin-bottom:16px;font-size:.83rem">DB Error: {perf["_error"]}</div>'
    elif perf['_rows_found'] == 0:
        debug_bar = '<div style="background:#78350f;color:#fcd34d;padding:10px 16px;border-radius:6px;margin-bottom:16px;font-size:.83rem">No data found in DB for these tickers — run db_daily_update.py to populate.</div>'

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
      .ix-section {{ margin-bottom: 32px; }}
      .ix-section h2 {{ font-size: .78rem; font-weight: 600; color: #777;
                       text-transform: uppercase; letter-spacing: .06em; margin-bottom: 14px; }}
    </style>

    {debug_bar}

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
    """
    return page_wrap('Indexes & ETFs', 'indexes', content)


def us_index_page(title, active_key, tickers, etf_ticker=''):
    """Generic page builder for US index tabs (Dow/Nasdaq/S&P/Russell)."""
    sparklines = get_us_sparklines_batch(tickers)
    latest     = get_us_latest_prices(tickers)
    with_data  = get_us_tickers_with_data(tickers)

    # ── Breadth calculation from sparklines ──────────────────────────────────
    def breadth(n):
        up = down = flat = no_data = 0
        for t in tickers:
            c = sparklines.get(t, [])
            if len(c) > n:
                if   c[-1] > c[-1-n]: up   += 1
                elif c[-1] < c[-1-n]: down += 1
                else:                 flat += 1
            else:
                no_data += 1
        total = up + down + flat
        up_pct   = round(up   / total * 100, 1) if total else 0
        down_pct = round(down / total * 100, 1) if total else 0
        flat_pct = round(100 - up_pct - down_pct, 1)
        return up, down, flat, up_pct, down_pct, flat_pct, total

    d_up,  d_dn,  d_fl,  d_up_pct,  d_dn_pct,  d_fl_pct,  d_tot  = breadth(1)
    w_up,  w_dn,  w_fl,  w_up_pct,  w_dn_pct,  w_fl_pct,  w_tot  = breadth(5)
    m_up,  m_dn,  m_fl,  m_up_pct,  m_dn_pct,  m_fl_pct,  m_tot  = breadth(21)

    rows_html = ''
    for ticker in tickers:
        closes  = sparklines.get(ticker, [])
        price   = latest.get(ticker)
        svg     = sparkline_svg(closes) if ticker in with_data else ''
        price_s = f'${price:,.2f}' if price else '—'
        day_chg = ''
        if len(closes) >= 2:
            pct = (closes[-1] - closes[-2]) / closes[-2] * 100
            col = '#22c55e' if pct >= 0 else '#ef4444'
            day_chg = f'<span style="color:{col};font-size:.78rem">{"+" if pct>=0 else ""}{pct:.2f}%</span>'
        rows_html += f"""
        <tr class="ux-row" data-ticker="{ticker}" style="cursor:{'pointer' if ticker in with_data else 'default'}">
          <td>
            <div style="display:flex;align-items:center;gap:12px">
              <strong style="color:#60a5fa;min-width:68px;font-size:1rem">{ticker}</strong>
              {svg}
            </div>
          </td>
          <td style="font-weight:700;color:#fff;font-size:1rem">{price_s}</td>
          <td style="font-size:.95rem;font-weight:600">{day_chg}</td>
        </tr>"""

    chart_js = """
    <script>
    document.querySelectorAll('.ux-row').forEach(row => {
      row.addEventListener('click', () => {
        const ticker = row.dataset.ticker;
        const existId = 'udrop-' + ticker;
        const exist = document.getElementById(existId);
        if (exist) { exist.remove(); row.classList.remove('active'); return; }
        document.querySelectorAll('.ux-drop').forEach(d => d.remove());
        document.querySelectorAll('.ux-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        const drop = document.createElement('tr');
        drop.id = existId; drop.className = 'ux-drop';
        drop.innerHTML = `<td colspan="3" style="background:#080a10;padding:16px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <span style="color:#fff;font-weight:700;font-size:1rem">${ticker} <span style="color:#555;font-size:.78rem">NYSE/NASDAQ</span></span>
            <span style="color:#555;font-size:.75rem" id="us-${ticker}">Loading...</span>
          </div>
          <div id="um-${ticker}" style="height:340px;background:#0a0c14;border-radius:6px"></div>
          <div id="uv-${ticker}" style="height:65px;background:#0a0c14;border-radius:6px;margin-top:3px"></div>
        </td>`;
        row.parentNode.insertBefore(drop, row.nextSibling);
        fetch('/api/us-chart/' + ticker)
          .then(r => r.json())
          .then(data => {
            if (data.error) { document.getElementById('us-' + ticker).textContent = data.error; return; }
            document.getElementById('us-' + ticker).textContent = data.bars + ' bars · ' + data.date_range;
            const chart = LightweightCharts.createChart(document.getElementById('um-' + ticker), {
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
            const barCount = data.ohlcv.length;
            chart.timeScale().setVisibleLogicalRange({ from: 0, to: barCount + Math.round(barCount * 0.9) });
            chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.12, bottom: 0.18 } });
            const vc = LightweightCharts.createChart(document.getElementById('uv-' + ticker), {
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
          .catch(e => { document.getElementById('us-' + ticker).textContent = 'Failed: ' + e; });
      });
    });
    </script>"""

    # ── Build donut cards HTML ────────────────────────────────────────────────
    donut_html = ''
    for period, up_pct, dn_pct, fl_pct, up, dn in [
        ('Day',   d_up_pct, d_dn_pct, d_fl_pct, d_up, d_dn),
        ('Week',  w_up_pct, w_dn_pct, w_fl_pct, w_up, w_dn),
        ('Month', m_up_pct, m_dn_pct, m_fl_pct, m_up, m_dn),
    ]:
        pid = period.lower()
        center_style = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:1.6rem;font-weight:800;color:#fff;white-space:nowrap'
        donut_html += (
            f'<div style="text-align:center">'
            f'<div style="font-size:.82rem;color:#aaa;font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">{period}</div>'
            f'<div style="position:relative;width:150px;height:150px">'
            f'<canvas id="donut-{pid}" width="150" height="150"></canvas>'
            f'<div style="{center_style}">{up_pct}%</div>'
            f'</div>'
            f'<div style="font-size:.88rem;margin-top:10px;font-weight:600">'
            f'<span style="color:#22c55e">&#9650; {up} up</span>'
            f'<span style="color:#555;margin:0 8px">/</span>'
            f'<span style="color:#ef4444">&#9660; {dn} down</span>'
            f'</div></div>'
        )

    etf_section = ''
    if etf_ticker:
        etf_section = f"""
        <div id="etf-chart-wrap">
          <div style="font-size:.78rem;color:#888;margin-bottom:8px;font-weight:600">
            {etf_ticker} &nbsp;<span style="color:#555;font-weight:400">— 60 Day</span>
          </div>
          <div id="etf-area" style="height:220px;background:#0a0c14;border-radius:8px"></div>
        </div>
        <script>
        (function(){{
          fetch('/api/us-chart/{etf_ticker}')
            .then(r=>r.json())
            .then(data=>{{
              if(data.error||!data.ohlcv) return;
              const recent = data.ohlcv.slice(-60);
              const LWC = LightweightCharts;
              const chart = LWC.createChart(document.getElementById('etf-area'),{{
                layout:{{background:{{color:'#0a0c14'}},textColor:'#555'}},
                grid:{{vertLines:{{color:'#12141e'}},horzLines:{{color:'#12141e'}}}},
                rightPriceScale:{{borderColor:'#1a1d2e'}},
                timeScale:{{borderColor:'#1a1d2e',timeVisible:false}},
                crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
                handleScroll:false, handleScale:false,
              }});
              const area = chart.addAreaSeries({{
                lineColor:'#3b82f6', topColor:'#3b82f644',
                bottomColor:'#3b82f600', lineWidth:2,
              }});
              area.setData(recent.map(b=>({{time:b.time,value:b.close}})));
              chart.timeScale().fitContent();
            }}).catch(()=>{{}});
        }})();
        </script>"""

    content = f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>

    <!-- Dashboard header -->
    <section style="margin-bottom:20px">

      {etf_section}

      <!-- Breadth donuts -->
      <div style="margin-top:18px">
        <p style="font-size:.88rem;color:#888;margin-bottom:14px">
          Percentage of <strong style="color:#fff">{title}</strong> stocks moving up or down over each time period
        </p>
        <div style="display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap">
          {donut_html}
        </div>
      </div>

      <div style="margin-top:14px;font-size:.8rem;color:#444">
        {len(with_data)} of {len(tickers)} tickers with data &nbsp;·&nbsp; click any row to expand chart
      </div>
    </section>

    <script>
    (function(){{
      const donuts = [
        {{ id:'donut-day',   up:{d_up_pct}, dn:{d_dn_pct}, fl:{d_fl_pct} }},
        {{ id:'donut-week',  up:{w_up_pct}, dn:{w_dn_pct}, fl:{w_fl_pct} }},
        {{ id:'donut-month', up:{m_up_pct}, dn:{m_dn_pct}, fl:{m_fl_pct} }},
      ];
      donuts.forEach(d => {{
        const ctx = document.getElementById(d.id).getContext('2d');
        new Chart(ctx, {{
          type: 'doughnut',
          data: {{
            datasets: [{{
              data: [d.up, d.dn, d.fl],
              backgroundColor: ['#22c55e','#ef4444','#1f2235'],
              borderWidth: 0,
              hoverOffset: 4,
            }}]
          }},
          options: {{
            cutout: '70%',
            animation: {{ animateRotate: true, duration: 1200, easing: 'easeInOutQuart' }},
            plugins: {{
              legend: {{ display: false }},
              tooltip: {{
                callbacks: {{
                  label: ctx => ['Up','Down','Flat'][ctx.dataIndex] + ': ' + ctx.parsed + '%'
                }}
              }}
            }}
          }}
        }});
      }});
    }})();
    </script>
    <section>
      <style>
        .ux-table {{ width:100%; border-collapse:collapse; font-size:.95rem; }}
        .ux-table th {{ text-align:left; padding:10px 14px; color:#777;
                       border-bottom:1px solid #2a2d3e; font-weight:500; cursor:pointer; user-select:none; font-size:.82rem; }}
        .ux-table th:hover {{ color:#aaa; }}
        .ux-table th.sort-asc::after  {{ content:' ▲'; font-size:.65rem; color:#60a5fa; }}
        .ux-table th.sort-desc::after {{ content:' ▼'; font-size:.65rem; color:#60a5fa; }}
        .ux-table td {{ padding:10px 14px; border-bottom:1px solid #151820; vertical-align:middle; }}
        .ux-table .ux-row:hover td {{ background:#1f2235; }}
        .ux-table .ux-row.active td {{ background:#1a2235; }}
        .ux-drop td {{ padding:0 !important; }}
      </style>
      <table class="ux-table">
        <thead><tr>
          <th onclick="sortUx(this)">Ticker</th>
          <th onclick="sortUx(this)">Price (USD)</th>
          <th onclick="sortUx(this)">Day %</th>
        </tr></thead>
        <tbody id="ux-tbody">{rows_html}</tbody>
      </table>
    </section>
    <script>
    function sortUx(th) {{
      const tbody = document.getElementById('ux-tbody');
      const idx = th.cellIndex;
      const asc = th.classList.contains('sort-desc');
      th.closest('thead').querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      const rows = Array.from(tbody.querySelectorAll('.ux-row'));
      rows.sort((a, b) => {{
        const av = a.cells[idx].textContent.trim();
        const bv = b.cells[idx].textContent.trim();
        const an = parseFloat(av.replace('$','').replace(',','')), bn = parseFloat(bv.replace('$','').replace(',',''));
        const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
        return asc ? cmp : -cmp;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }}
    </script>
    {chart_js}"""

    return page_wrap(title, active_key, content)


@app.route('/dow')
def dow_page():
    return us_index_page('Dow Jones 30', 'dow', DOW_30, etf_ticker='DIA')


@app.route('/nasdaq')
def nasdaq_page():
    return us_index_page('Nasdaq 100', 'nasdaq', NASDAQ_100, etf_ticker='QQQ')


@app.route('/sp500')
def sp500_page():
    return us_index_page('S&P 500', 'sp500', SP500_TICKERS, etf_ticker='SPY')


@app.route('/russell')
def russell_page():
    known = set(DOW_30) | set(NASDAQ_100) | set(SP500_TICKERS)
    all_us = get_us_all_tickers_with_data()
    russell_tickers = sorted(t for t in all_us if t not in known)
    return us_index_page('Russell / Small Caps', 'russell', russell_tickers, etf_ticker='IWM')


# ─── How It Works ─────────────────────────────────────────────────────────────

VIDEO_URL_FILE = os.path.join(BASE_DIR, 'how_it_works_video.txt')

def get_video_url():
    if os.path.exists(VIDEO_URL_FILE):
        with open(VIDEO_URL_FILE) as f:
            return f.read().strip()
    return ''

def save_video_url(url):
    with open(VIDEO_URL_FILE, 'w') as f:
        f.write(url.strip())


@app.route('/how-it-works', methods=['GET', 'POST'])
def how_it_works():
    admin = is_admin()
    if request.method == 'POST' and admin:
        save_video_url(request.form.get('video_url', ''))
        return redirect('/how-it-works')

    video_url = get_video_url()

    # Convert Loom share URL to embed URL if needed
    if 'loom.com/share/' in video_url:
        video_url = video_url.replace('loom.com/share/', 'loom.com/embed/')

    if video_url:
        video_html = f"""
        <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin-bottom:40px;border:1px solid #2a2d3e">
          <iframe src="{video_url}" frameborder="0" allowfullscreen
            style="position:absolute;top:0;left:0;width:100%;height:100%"></iframe>
        </div>"""
    else:
        video_html = f"""
        <div style="background:#13151f;border:2px dashed #2a2d3e;border-radius:12px;padding:60px 24px;text-align:center;margin-bottom:40px">
          <div style="font-size:2.5rem;margin-bottom:12px">🎬</div>
          <div style="color:#555;font-size:.9rem">Video coming soon</div>
          {'<p style="color:#444;font-size:.8rem;margin-top:8px">Paste your Loom URL in the form below to add it.</p>' if admin else ''}
        </div>"""

    steps = [
        ('🔍', 'Scanner Finds the Setup',
         'Our scanner watches thousands of stocks every day looking for one specific pattern — price compressing into a tight channel. Most stocks are ignored. We only want the ones coiling up.',
         '#818cf8'),
        ('📊', 'Channel Printing',
         'When a stock\'s price squeezes into a narrow range and the moving averages compress together, that\'s called a channel printing. It\'s the market holding its breath before a move.',
         '#60a5fa'),
        ('⚡', 'Signal Triggers',
         'Once the channel is confirmed, we wait for the momentum indicators to align — the Fader line turning green and the Force Index pulling back. When all conditions line up together, that\'s our entry signal.',
         '#22c55e'),
        ('🎯', 'Entry at the 25% Level',
         'We enter at the 25% level of the stock\'s price range — a proven support zone. Stop below the range low, target at the 75% level. Clean risk/reward every time.',
         '#f59e0b'),
    ]

    step_cards = ''
    for icon, title, desc, color in steps:
        step_cards += f"""
        <div style="background:#13151f;border:1px solid #2a2d3e;border-radius:12px;padding:28px 24px">
          <div style="font-size:2rem;margin-bottom:12px">{icon}</div>
          <div style="font-size:1rem;font-weight:700;color:{color};margin-bottom:10px">{title}</div>
          <div style="color:#999;font-size:.87rem;line-height:1.7">{desc}</div>
        </div>"""

    admin_form = ''
    if admin:
        admin_form = f"""
        <div style="background:#13151f;border:1px solid #2a2d3e;border-radius:10px;padding:20px 24px;margin-top:40px">
          <div style="font-size:.75rem;color:#555;text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px">Admin — Update Video</div>
          <form method="POST" style="display:flex;gap:10px;align-items:center">
            <input name="video_url" value="{get_video_url()}" placeholder="Paste Loom share URL here..."
              style="flex:1;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                     color:#e0e0e0;padding:9px 12px;font-size:.85rem">
            <button type="submit" class="btn btn-blue" style="white-space:nowrap">Save Video</button>
          </form>
        </div>"""

    content = f"""
    <style>
      .step-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:16px; margin-bottom:40px; }}
    </style>

    <!-- Hero -->
    <div style="text-align:center;margin-bottom:40px;padding:20px 0">
      <h1 style="font-size:2rem;font-weight:800;margin-bottom:12px">How Jimmy Trades</h1>
      <p style="color:#888;font-size:1rem;max-width:560px;margin:0 auto;line-height:1.7">
        A simple, repeatable system for finding stocks before they move.
        No guessing. No noise. Just one pattern, executed consistently.
      </p>
    </div>

    <!-- Video -->
    {video_html}

    <!-- Steps -->
    <h2 style="font-size:.8rem;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px">The System — 4 Steps</h2>
    <div class="step-grid">
      {step_cards}
    </div>

    <!-- CTA -->
    <div style="background:linear-gradient(135deg,#1a1d2e,#13151f);border:1px solid #2a2d3e;border-radius:14px;padding:40px 32px;text-align:center;margin-bottom:24px">
      <div style="font-size:1.4rem;font-weight:800;margin-bottom:10px">See It In Action</div>
      <p style="color:#888;font-size:.9rem;max-width:480px;margin:0 auto 24px">
        Follow the live $100,000 paper trading account. Every buy and sell is posted in real time so you can see exactly how the system performs.
      </p>
      <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
        <a href="/picks" class="btn btn-green" style="font-size:.95rem;padding:11px 28px">View US Picks →</a>
        <a href="/asx/picks" class="btn btn-blue" style="font-size:.95rem;padding:11px 28px">View ASX Picks →</a>
      </div>
    </div>

    {admin_form}
    """

    return page_wrap('How It Works', 'howitworks', content)


# ─── Dividend Picks ───────────────────────────────────────────────────────────

@app.route('/dividend')
def dividend_page():
    stocks = get_all_dividend_stocks()
    admin  = is_admin()

    # Get latest prices from DB — check both US (prices) and ASX (asx_prices) tables
    tickers = [s['ticker'] for s in stocks]
    prices  = {}
    if tickers:
        try:
            conn = get_connection()
            fmt  = ','.join(['%s'] * len(tickers))
            with conn.cursor() as cur:
                # US prices table
                cur.execute(f"""
                    SELECT p.ticker, p.close
                    FROM prices p
                    INNER JOIN (
                        SELECT ticker, MAX(date) AS md FROM prices
                        WHERE ticker IN ({fmt}) GROUP BY ticker
                    ) latest ON p.ticker=latest.ticker AND p.date=latest.md
                """, tickers)
                for t, c in cur.fetchall():
                    prices[t] = float(c)
                # ASX prices table (fills in any not found above)
                cur.execute(f"""
                    SELECT p.ticker, p.close
                    FROM asx_prices p
                    INNER JOIN (
                        SELECT ticker, MAX(date) AS md FROM asx_prices
                        WHERE ticker IN ({fmt}) GROUP BY ticker
                    ) latest ON p.ticker=latest.ticker AND p.date=latest.md
                """, tickers)
                for t, c in cur.fetchall():
                    if t not in prices:
                        prices[t] = float(c)
            conn.close()
        except Exception:
            pass

    # ── Stock list rows ────────────────────────────────────────────────────────
    list_rows = ''
    for s in stocks:
        price    = prices.get(s['ticker'])
        price_td = f'${price:,.2f}' if price else '—'
        yld      = f"{s['dividend_yield']:.2f}%" if s['dividend_yield'] else '—'
        yrs      = str(s['years_div_growth']) if s['years_div_growth'] else '—'
        target   = f"${s['target_price']:,.2f}" if s['target_price'] else '—'
        sector   = s['sector'] or ''
        edit_btn = f'<a href="/dividend/edit/{s["id"]}" style="color:#60a5fa;font-size:.75rem;margin-left:8px">edit</a>' if admin else ''
        sticker  = s['ticker']
        del_btn  = f'<a href="/dividend/delete/{s["id"]}" onclick="return confirm(\'Remove {sticker}?\')" style="color:#ef4444;font-size:.75rem;margin-left:6px">×</a>' if admin else ''

        list_rows += f"""
        <tr class="div-row" data-id="{s['id']}" onclick="showThesis({s['id']})">
          <td style="padding:12px 14px;font-weight:700;color:#e0e0e0;white-space:nowrap">
            {s['ticker']}{edit_btn}{del_btn}
          </td>
          <td style="padding:12px 8px;color:#aaa;font-size:.82rem">{s['company']}</td>
          <td style="padding:12px 8px;color:#888;font-size:.78rem">{sector}</td>
          <td style="padding:12px 8px;color:#22c55e;font-weight:600;text-align:right">{yld}</td>
          <td style="padding:12px 8px;color:#60a5fa;text-align:right">{price_td}</td>
          <td style="padding:12px 8px;color:#f59e0b;text-align:right">{target}</td>
          <td style="padding:12px 8px;color:#888;text-align:center;font-size:.8rem">{yrs} yrs</td>
        </tr>"""

    if not list_rows:
        list_rows = '<tr><td colspan="7" style="padding:24px;text-align:center;color:#555">No stocks added yet.</td></tr>'

    # ── Thesis panels (hidden, shown on click) ─────────────────────────────────
    thesis_panels = ''
    for s in stocks:
        points = [
            ('Business Moat',        s['thesis_moat'],     '#818cf8'),
            ('Dividend Track Record', s['thesis_dividend'], '#22c55e'),
            ('Payout Sustainability', s['thesis_sustain'],  '#f59e0b'),
            ('Price Trend',           s['thesis_trend'],    '#60a5fa'),
            ('Why Now',               s['thesis_why_now'],  '#f472b6'),
        ]
        pts_html = ''
        for title, body, color in points:
            txt = body if body else '<span style="color:#555;font-style:italic">Not yet written.</span>'
            pts_html += f"""
            <div style="margin-bottom:18px">
              <div style="font-size:.7rem;font-weight:700;letter-spacing:.08em;color:{color};text-transform:uppercase;margin-bottom:4px">{title}</div>
              <div style="color:#ccc;font-size:.88rem;line-height:1.6">{txt}</div>
            </div>"""

        price    = prices.get(s['ticker'])
        yld      = f"{s['dividend_yield']:.2f}%" if s['dividend_yield'] else '—'
        pr       = f"{s['payout_ratio']:.0f}%" if s['payout_ratio'] else '—'
        yrs      = f"{s['years_div_growth']} years" if s['years_div_growth'] else '—'
        price_td = f'${price:,.2f}' if price else '—'
        target   = f"${s['target_price']:,.2f}" if s['target_price'] else '—'
        edit_lnk  = f'<a href="/dividend/edit/{s["id"]}" class="btn btn-blue" style="font-size:.78rem;padding:5px 14px">Edit Thesis</a>' if admin else ''
        chart_img = f'<img src="/dividend/image/{s["image_path"]}" onclick="openLightbox(this.src)" style="width:100%;border-radius:8px;margin-bottom:18px;border:1px solid #2a2d3e;cursor:zoom-in">' if s.get('image_path') else ''

        thesis_panels += f"""
        <div id="thesis-{s['id']}" class="thesis-panel" style="display:none">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px">
            <div>
              <div style="font-size:1.4rem;font-weight:800;color:#e0e0e0">{s['ticker']}</div>
              <div style="color:#888;font-size:.85rem">{s['company']}</div>
              <div style="color:#555;font-size:.75rem;margin-top:2px">{s['sector']}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:1.1rem;font-weight:700;color:#60a5fa">{price_td}</div>
              <div style="color:#22c55e;font-size:.85rem;font-weight:600">Yield {yld}</div>
              <div style="color:#aaa;font-size:.75rem">Target {target}</div>
            </div>
          </div>
          {chart_img}
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px">
            <div class="card" style="padding:10px 14px;text-align:center">
              <div style="font-size:.68rem;color:#555;text-transform:uppercase;letter-spacing:.06em">Div Yield</div>
              <div style="font-size:1.1rem;font-weight:700;color:#22c55e">{yld}</div>
            </div>
            <div class="card" style="padding:10px 14px;text-align:center">
              <div style="font-size:.68rem;color:#555;text-transform:uppercase;letter-spacing:.06em">Payout Ratio</div>
              <div style="font-size:1.1rem;font-weight:700;color:#f59e0b">{pr}</div>
            </div>
            <div class="card" style="padding:10px 14px;text-align:center">
              <div style="font-size:.68rem;color:#555;text-transform:uppercase;letter-spacing:.06em">Div Growth</div>
              <div style="font-size:1.1rem;font-weight:700;color:#818cf8">{yrs}</div>
            </div>
          </div>
          <h3 style="font-size:.9rem;color:#555;margin-bottom:14px;text-transform:uppercase;letter-spacing:.08em">Jimmy's Thesis</h3>
          {pts_html}
          <div style="margin-top:16px">{edit_lnk}</div>
        </div>"""

    add_btn = '<a href="/dividend/add" class="btn btn-green" style="margin-bottom:16px">+ Add Stock</a>' if admin else ''

    content = f"""
    <style>
      .div-row {{ cursor:pointer; border-bottom:1px solid #151820; transition:background .15s; }}
      .div-row:hover td {{ background:#1a1d2e; }}
      .div-row.active td {{ background:#1f2235; }}
      .thesis-panel {{ background:#13151f; border:1px solid #2a2d3e; border-radius:10px; padding:22px; }}
    </style>

    <div style="display:flex;gap:20px;align-items:flex-start">

      <!-- Left: stock list -->
      <div style="flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h2 style="margin:0">Long-Term Dividend Picks</h2>
          {add_btn}
        </div>
        <p style="color:#666;font-size:.83rem;margin-bottom:16px">
          Stocks selected for long-term holding (10–20 years). Click any row to read the thesis.
        </p>
        <div class="card" style="padding:0;overflow:hidden">
          <table style="width:100%;border-collapse:collapse;font-size:.84rem">
            <thead>
              <tr style="border-bottom:2px solid #2a2d3e">
                <th style="text-align:left;padding:10px 14px;color:#555;font-weight:500">Ticker</th>
                <th style="text-align:left;padding:10px 8px;color:#555;font-weight:500">Company</th>
                <th style="text-align:left;padding:10px 8px;color:#555;font-weight:500">Sector</th>
                <th style="text-align:right;padding:10px 8px;color:#555;font-weight:500">Yield</th>
                <th style="text-align:right;padding:10px 8px;color:#555;font-weight:500">Price</th>
                <th style="text-align:right;padding:10px 8px;color:#555;font-weight:500">Target</th>
                <th style="text-align:center;padding:10px 8px;color:#555;font-weight:500">Div Growth</th>
              </tr>
            </thead>
            <tbody>{list_rows}</tbody>
          </table>
        </div>
      </div>

      <!-- Lightbox overlay -->
      <div id="div-lightbox" onclick="closeLightbox()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9999;cursor:zoom-out;align-items:center;justify-content:center">
        <img id="div-lightbox-img" src="" style="max-width:92vw;max-height:92vh;border-radius:8px;box-shadow:0 0 60px rgba(0,0,0,.8)">
      </div>

      <!-- Right: thesis panel -->
      <div style="width:380px;flex-shrink:0;position:sticky;top:80px">
        <div id="thesis-placeholder" style="background:#13151f;border:1px solid #1e2130;border-radius:10px;padding:40px 24px;text-align:center;color:#444">
          <div style="font-size:2rem;margin-bottom:10px">📋</div>
          <div>Click a stock to read the thesis</div>
        </div>
        {thesis_panels}
      </div>

    </div>

    <script>
      function showThesis(id) {{
        document.querySelectorAll('.thesis-panel').forEach(p => p.style.display = 'none');
        document.querySelectorAll('.div-row').forEach(r => r.classList.remove('active'));
        document.getElementById('thesis-placeholder').style.display = 'none';
        document.getElementById('thesis-' + id).style.display = 'block';
        document.querySelector('.div-row[data-id="' + id + '"]').classList.add('active');
      }}
      function openLightbox(src) {{
        var lb = document.getElementById('div-lightbox');
        document.getElementById('div-lightbox-img').src = src;
        lb.style.display = 'flex';
      }}
      function closeLightbox() {{
        document.getElementById('div-lightbox').style.display = 'none';
      }}
      document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') closeLightbox();
      }});
    </script>
    """

    return page_wrap('Dividend Picks', 'dividend', content)


def _handle_dividend_image():
    """Save uploaded chart image, return filename or None."""
    file = request.files.get('chart_image')
    if file and file.filename:
        ext      = os.path.splitext(file.filename)[1].lower()
        filename = f"div_{uuid.uuid4().hex}{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        file.save(os.path.join(UPLOADS_DIR, filename))
        return filename
    return None


@app.route('/dividend/add', methods=['GET', 'POST'])
def dividend_add():
    if not is_admin():
        return redirect('/dividend')
    error = ''
    if request.method == 'POST':
        image_path = _handle_dividend_image()
        ok, err = upsert_dividend_stock(
            ticker=request.form.get('ticker','').strip(),
            company=request.form.get('company','').strip(),
            sector=request.form.get('sector','').strip(),
            dividend_yield=request.form.get('dividend_yield') or None,
            payout_ratio=request.form.get('payout_ratio') or None,
            years_div_growth=request.form.get('years_div_growth') or None,
            target_price=request.form.get('target_price') or None,
            thesis_moat=request.form.get('thesis_moat','').strip(),
            thesis_dividend=request.form.get('thesis_dividend','').strip(),
            thesis_sustain=request.form.get('thesis_sustain','').strip(),
            thesis_trend=request.form.get('thesis_trend','').strip(),
            thesis_why_now=request.form.get('thesis_why_now','').strip(),
            image_path=image_path,
            display_order=int(request.form.get('display_order') or 0),
        )
        if ok:
            return redirect('/dividend')
        error = err
    return page_wrap('Add Dividend Stock', 'dividend', _dividend_form(error=error))


@app.route('/dividend/edit/<int:stock_id>', methods=['GET', 'POST'])
def dividend_edit(stock_id):
    if not is_admin():
        return redirect('/dividend')
    stock = get_dividend_stock(stock_id)
    if not stock:
        return redirect('/dividend')
    error = ''
    if request.method == 'POST':
        image_path = _handle_dividend_image()
        ok, err = upsert_dividend_stock(
            ticker=request.form.get('ticker','').strip(),
            company=request.form.get('company','').strip(),
            sector=request.form.get('sector','').strip(),
            dividend_yield=request.form.get('dividend_yield') or None,
            payout_ratio=request.form.get('payout_ratio') or None,
            years_div_growth=request.form.get('years_div_growth') or None,
            target_price=request.form.get('target_price') or None,
            thesis_moat=request.form.get('thesis_moat','').strip(),
            thesis_dividend=request.form.get('thesis_dividend','').strip(),
            thesis_sustain=request.form.get('thesis_sustain','').strip(),
            thesis_trend=request.form.get('thesis_trend','').strip(),
            thesis_why_now=request.form.get('thesis_why_now','').strip(),
            image_path=image_path,
            display_order=int(request.form.get('display_order') or 0),
            stock_id=stock_id,
        )
        if ok:
            return redirect('/dividend')
        error = err
    return page_wrap('Edit Dividend Stock', 'dividend', _dividend_form(stock=stock, error=error))


@app.route('/dividend/delete/<int:stock_id>')
def dividend_delete(stock_id):
    if not is_admin():
        return redirect('/dividend')
    delete_dividend_stock(stock_id)
    return redirect('/dividend')


@app.route('/dividend/image/<filename>')
def dividend_image(filename):
    return send_from_directory(UPLOADS_DIR, filename)


def _dividend_form(stock=None, error=''):
    s = stock or {}
    def v(k, default=''): return s.get(k, default) or default
    def textarea(name, label, color, placeholder):
        return f"""
        <div style="margin-bottom:16px">
          <label style="display:block;font-size:.75rem;font-weight:700;color:{color};
                        text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">{label}</label>
          <textarea name="{name}" rows="4" placeholder="{placeholder}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:10px 12px;font-size:.85rem;resize:vertical;box-sizing:border-box"
          >{v(name)}</textarea>
        </div>"""

    err_html = f'<div style="color:#ef4444;margin-bottom:12px">{error}</div>' if error else ''
    title    = 'Edit Stock' if stock else 'Add Stock'

    return f"""
    <h2>{title}</h2>
    {err_html}
    <form method="POST" enctype="multipart/form-data" style="max-width:700px">
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:12px;margin-bottom:16px">
        <div>
          <label style="color:#888;font-size:.78rem">Ticker</label>
          <input name="ticker" value="{v('ticker')}" required
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.9rem;box-sizing:border-box">
        </div>
        <div>
          <label style="color:#888;font-size:.78rem">Company Name</label>
          <input name="company" value="{v('company')}" required
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.9rem;box-sizing:border-box">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:12px;margin-bottom:20px">
        <div>
          <label style="color:#888;font-size:.78rem">Sector</label>
          <input name="sector" value="{v('sector')}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.85rem;box-sizing:border-box">
        </div>
        <div>
          <label style="color:#888;font-size:.78rem">Div Yield %</label>
          <input name="dividend_yield" type="number" step="0.01" value="{v('dividend_yield')}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.85rem;box-sizing:border-box">
        </div>
        <div>
          <label style="color:#888;font-size:.78rem">Payout Ratio %</label>
          <input name="payout_ratio" type="number" step="0.1" value="{v('payout_ratio')}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.85rem;box-sizing:border-box">
        </div>
        <div>
          <label style="color:#888;font-size:.78rem">Years Div Growth</label>
          <input name="years_div_growth" type="number" value="{v('years_div_growth')}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.85rem;box-sizing:border-box">
        </div>
        <div>
          <label style="color:#888;font-size:.78rem">Target Price</label>
          <input name="target_price" type="number" step="0.01" value="{v('target_price')}"
            style="width:100%;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;
                   color:#e0e0e0;padding:9px 12px;font-size:.85rem;box-sizing:border-box">
        </div>
      </div>

      <h3 style="color:#555;font-size:.8rem;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px">
        Jimmy's 5-Point Thesis
      </h3>
      {textarea('thesis_moat',     'Business Moat',         '#818cf8', 'Does it have pricing power? Will it still exist in 20 years?')}
      {textarea('thesis_dividend', 'Dividend Track Record',  '#22c55e', 'How many years of consecutive dividend growth?')}
      {textarea('thesis_sustain',  'Payout Sustainability',  '#f59e0b', 'Payout ratio healthy? Free cash flow covers it?')}
      {textarea('thesis_trend',    'Price Trend',            '#60a5fa', 'Is the stock price trending up over 10 years?')}
      {textarea('thesis_why_now',  'Why Now',                '#f472b6', 'Is it at a good entry point? Why buy at this price?')}

      <div style="margin-bottom:20px">
        <label style="display:block;font-size:.75rem;font-weight:700;color:#aaa;
                      text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Chart Image</label>
        {'<img src="/dividend/image/' + v('image_path') + '" style="width:100%;border-radius:6px;margin-bottom:8px;border:1px solid #2a2d3e">' if v('image_path') else ''}
        <input type="file" name="chart_image" accept="image/*"
          style="color:#aaa;font-size:.83rem">
        <div style="color:#555;font-size:.75rem;margin-top:4px">Upload a screenshot of your chart (PNG, JPG). Leave blank to keep existing image.</div>
      </div>

      <div style="display:flex;gap:10px;margin-top:8px">
        <button type="submit" class="btn btn-green">Save Stock</button>
        <a href="/dividend" class="btn" style="background:#2a2d3e;color:#aaa">Cancel</a>
      </div>
    </form>
    """


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


# ─── Admin Hub ────────────────────────────────────────────────────────────────

@app.route('/admin')
def admin_hub():
    if not is_admin():
        return redirect('/')

    with _job_lock:
        running = _job_running
        jname   = _job_name

    stats           = get_db_stats()
    last_refresh    = get_last_refresh_date()
    refreshed_today = already_refreshed_today()
    s               = get_user_stats()

    # ── Button states ─────────────────────────────────────────────────────────
    def job_btn(label, href, style='btn-blue', confirm=None):
        if running:
            return f'<span class="btn btn-off">{label}</span>'
        c = f' onclick="return confirm(\'{confirm}\')"' if confirm else ''
        return f'<a href="{href}" class="btn {style}"{c}>{label}</a>'

    refresh_btn  = job_btn('⟳ Update US & ASX Prices', '/run-refresh', 'btn-green')
    daily_btn    = job_btn('Run Daily Update', '/run-daily')
    initial_btn  = job_btn('Run Initial Download', '/run-initial', 'btn-amber',
                           'This downloads 5 years for all tickers. Takes 1–2 hours. Continue?')
    asx_dl_btn   = job_btn('Download / Update ASX Data', '/asx/download')
    channel_btn  = job_btn('▶ Run Channel Scan', '/run-scan')
    fader_btn    = job_btn('▶ Run Fader Scan', '/run-fader')
    efi_btn      = job_btn('▶ Run EFI Scan', '/run-efi')
    range_btn    = job_btn('▶ Run Range Scan', '/range/run')
    wick_btn     = job_btn('▶ Run Wick Scan', '/run-wick')

    refresh_note = f'Last updated: {last_refresh}' if last_refresh else 'Not updated today'

    # ── Job status bar ────────────────────────────────────────────────────────
    if running:
        status_bar = f'<div style="background:#78350f;color:#fcd34d;padding:12px 18px;border-radius:8px;margin-bottom:24px;font-weight:600">⚙ {jname} is running… <a href="/log-view" style="color:#fcd34d;margin-left:12px">View log →</a></div>'
    else:
        status_bar = '<div style="background:#052e16;color:#86efac;padding:12px 18px;border-radius:8px;margin-bottom:24px;font-weight:600">● All jobs idle</div>'

    # ── Last scan summaries ───────────────────────────────────────────────────
    ch_last   = load_last_results()
    fd_last   = load_last_fader_results()
    ef_last   = load_last_efi_results()
    wick_last = load_last_wick_results()

    def scan_summary(last, results_url):
        if not last:
            return '<span style="color:#555;font-size:.8rem">No scan run yet</span>'
        d = last.get('scan_date','?')
        t = last.get('total', last.get('count', '?'))
        return f'<span style="color:#aaa;font-size:.8rem">Last: {d} — {t} results &nbsp;<a href="{results_url}">View →</a></span>'

    # ── User analytics rows ───────────────────────────────────────────────────
    user_rows = ''
    for u in s['users']:
        q_color = '#60a5fa' if u['q_count'] > 0 else '#555'
        user_rows += f"""<tr>
          <td style="color:#aaa;font-size:.78rem">{u['id']}</td>
          <td><strong>{u['username']}</strong></td>
          <td style="color:#777;font-size:.83rem">{u['email']}</td>
          <td style="color:#aaa;font-size:.83rem">{u['created_date']}</td>
          <td style="color:{q_color};font-weight:700;text-align:center">{u['q_count']}</td>
          <td style="color:#777;font-size:.83rem">{u['last_question']}</td>
        </tr>"""

    # ── Log preview ───────────────────────────────────────────────────────────
    log_text = get_log()
    log_tail  = '\n'.join(log_text.splitlines()[-30:])

    content = f"""
    <style>
      .admin-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; }}
      .admin-grid3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; margin-bottom:20px; }}
      .tool-card {{ background:#1a1d2e; border:1px solid #2a2d3e; border-radius:8px; padding:20px; }}
      .tool-card h3 {{ font-size:.72rem; font-weight:600; color:#777; text-transform:uppercase;
                       letter-spacing:.06em; margin-bottom:14px; }}
      .a-table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
      .a-table th {{ text-align:left; padding:9px 12px; color:#555; border-bottom:1px solid #2a2d3e; font-weight:500; }}
      .a-table td {{ padding:9px 12px; border-bottom:1px solid #151820; }}
      .a-table tr:hover td {{ background:#1f2235; }}
    </style>

    {status_bar}

    <!-- DB stats -->
    <div class="admin-grid3" style="margin-bottom:20px">
      <div class="card">
        <div class="stat-label">Tickers in DB</div>
        <div class="stat-value">{stats['tickers']:,}</div>
        <div class="stat-sub">{stats['rows']} total rows</div>
      </div>
      <div class="card">
        <div class="stat-label">Latest Data</div>
        <div class="stat-value" style="font-size:1.2rem">{stats['latest']}</div>
        <div class="stat-sub">{refresh_note}</div>
      </div>
      <div class="card">
        <div class="stat-label">Registered Users</div>
        <div class="stat-value">{s['total_users']}</div>
        <div class="stat-sub">{s['new_this_week']} new this week · {s['pending']} pending questions</div>
      </div>
    </div>

    <!-- Price data + ASX -->
    <div class="admin-grid">
      <div class="tool-card">
        <h3>Price Data — US &amp; ASX</h3>
        <div class="btn-row" style="margin-bottom:10px">
          {refresh_btn}
        </div>
        <div class="btn-row" style="margin-bottom:10px">
          {daily_btn}
          {asx_dl_btn}
        </div>
        <div class="btn-row">
          {initial_btn}
        </div>
        <p class="note" style="margin-top:10px">Initial download takes 1–2 hours for all tickers.</p>
      </div>

      <!-- Scanners -->
      <div class="tool-card">
        <h3>Scanners</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div>
            <div class="btn-row" style="margin-bottom:6px">{channel_btn}</div>
            {scan_summary(ch_last, '/results')}
          </div>
          <div>
            <div class="btn-row" style="margin-bottom:6px">{fader_btn}</div>
            {scan_summary(fd_last, '/fader')}
          </div>
          <div>
            <div class="btn-row" style="margin-bottom:6px">{efi_btn}</div>
            {scan_summary(ef_last, '/efi')}
          </div>
          <div>
            <div class="btn-row" style="margin-bottom:6px">{range_btn}</div>
            {scan_summary(None, '/range')}
          </div>
          <div>
            <div class="btn-row" style="margin-bottom:6px">{wick_btn}</div>
            {scan_summary(wick_last, '/wick')}
          </div>
        </div>
      </div>
    </div>

    <!-- Scanner result links -->
    <section style="margin-bottom:20px">
      <h2>Scanner Results &amp; Tools</h2>
      <div class="btn-row">
        <a href="/results" class="btn btn-blue" style="font-size:.82rem">Channel Results</a>
        <a href="/fader"   class="btn btn-blue" style="font-size:.82rem">Fader Results</a>
        <a href="/efi"     class="btn btn-blue" style="font-size:.82rem">EFI Results</a>
        <a href="/range"   class="btn btn-blue" style="font-size:.82rem">Range Levels</a>
        <a href="/scan"    class="btn btn-blue" style="font-size:.82rem">Channel Scanner</a>
        <a href="/wick"     class="btn btn-blue" style="font-size:.82rem">Wick Scanner</a>
        <a href="/log-view" class="btn btn-blue" style="font-size:.82rem">Full Log</a>
        <a href="/ask"     class="btn btn-blue" style="font-size:.82rem">Ask Jimmy (Q&amp;A)</a>
      </div>
    </section>

    <!-- Log tail -->
    <section style="margin-bottom:20px">
      <h2>Log <span style="color:#555;font-weight:400;text-transform:none;letter-spacing:0;font-size:.75rem">(last 30 lines · <a href="/log-view">full log →</a>)</span></h2>
      <pre style="max-height:220px">{log_tail.replace('<','&lt;')}</pre>
    </section>

    <!-- Users -->
    <section>
      <h2>Registered Users ({s['total_users']}) &nbsp;
        <span style="color:{'#f59e0b' if s['pending']>0 else '#555'};font-weight:400;text-transform:none;letter-spacing:0;font-size:.78rem">
          {f'{s["pending"]} pending questions — <a href="/ask">answer →</a>' if s['pending'] else 'No pending questions'}
        </span>
      </h2>
      {'<table class="a-table"><thead><tr><th>#</th><th>Username</th><th>Email</th><th>Joined</th><th style="text-align:center">Questions</th><th>Last Question</th></tr></thead><tbody>' + user_rows + '</tbody></table>' if user_rows else '<p class="note">No users registered yet.</p>'}
    </section>
    """

    return page_wrap('Admin', 'admin', content, auto_refresh=running)


if __name__ == '__main__':
    app.run(debug=True)
