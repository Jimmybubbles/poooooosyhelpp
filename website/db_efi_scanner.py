"""
DB EFI SCANNER
==============
Daily-chart scanner. Three conditions must ALL be true:

  1. Channel printing  — EMA(5)/EMA(26) compressed within ATR(50)*0.4,
                         at least 5 of last 10 bars.

  2. EFI normalized price > 0  — price is above the BB basis line.

  3. EFI histogram < 0         — histogram is pulling back below zero
                                  (pullback in trend setup).

Reads directly from the MySQL prices table (same as db_fader_scanner).

Usage:
    python db_efi_scanner.py
"""

import pandas as pd
import numpy as np
import pymysql
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from EFI_Indicator import EFI_Indicator

# Reuse channel check from fader scanner
from db_fader_scanner import is_channel_printing

MIN_BARS    = 100
RESULTS_FILE = os.path.join(BASE_DIR, 'efi_scan_results.json')


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def get_all_tickers(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")
        return [row[0] for row in cur.fetchall()]


def get_ticker_data(conn, ticker):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM prices WHERE ticker = %s ORDER BY date ASC
        """, (ticker,))
        rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0)
    return df.dropna(subset=['Open', 'High', 'Low', 'Close'])


# ── Per-ticker scan ───────────────────────────────────────────────────────────

def scan_ticker(conn, ticker):
    df = get_ticker_data(conn, ticker)
    if df is None or len(df) < MIN_BARS:
        return None

    current_price = float(df['Close'].iloc[-1])
    if current_price < 0.50:
        return None

    # 1. Channel must be printing
    # is_channel_printing expects lowercase columns — make a view
    df_lower = df.rename(columns={'Open': 'open', 'High': 'high',
                                   'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    if not is_channel_printing(df_lower):
        return None

    # 2 & 3. EFI conditions
    try:
        indicator = EFI_Indicator()
        results   = indicator.calculate(df)

        norm_price = float(results['normalized_price'].iloc[-1])
        histogram  = float(results['histogram'].iloc[-1])
        force_idx  = float(results['force_index'].iloc[-1])
        fi_color   = results['fi_color'].iloc[-1]

        # normalized price > 0 AND histogram < 0
        if not (norm_price > 0 and histogram < 0):
            return None

    except Exception:
        return None

    return {
        'ticker':      ticker,
        'price':       round(current_price, 4),
        'norm_price':  round(norm_price, 4),
        'histogram':   round(histogram, 4),
        'force_index': round(force_idx, 4),
        'fi_color':    fi_color,
    }


# ── Full scan ─────────────────────────────────────────────────────────────────

def run_efi_scan(log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)

    log(f"EFI Scanner started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log("Conditions: channel printing + normalized price > 0 + histogram < 0\n\n")

    conn    = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    results = []
    for i, ticker in enumerate(tickers, 1):
        try:
            result = scan_ticker(conn, ticker)
            if result:
                results.append(result)
        except Exception:
            pass

        if i % 500 == 0:
            log(f"  Progress: {i}/{len(tickers)} — {len(results)} hits so far\n")

        if i % 1000 == 0:
            conn.close()
            conn = get_connection()

    conn.close()

    # Sort: strongest norm_price first (most extended above basis)
    results.sort(key=lambda x: x['norm_price'], reverse=True)

    log(f"\nScan complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log(f"Total setups found: {len(results)}\n")

    payload = {
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total':     len(results),
        'results':   results,
    }
    with open(RESULTS_FILE, 'w') as f:
        json.dump(payload, f)

    return results


def load_last_efi_results():
    if not os.path.exists(RESULTS_FILE):
        return None
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except Exception:
        return None


if __name__ == '__main__':
    run_efi_scan(log_callback=print)
