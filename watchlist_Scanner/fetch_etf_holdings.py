"""
FETCH ETF HOLDINGS
==================
Downloads current holdings for all 11 SPDR sector ETFs from SSGA
and outputs a TradingView-ready watchlist for each sector.

Usage:
    python fetch_etf_holdings.py

Output files saved to: watchlist_Scanner/etf_holdings/
"""

import requests
import pandas as pd
import os
import sys
from io import BytesIO
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'etf_holdings')
os.makedirs(OUTPUT_DIR, exist_ok=True)

SECTOR_ETFS = [
    ('XLK',  'Technology'),
    ('XLF',  'Financials'),
    ('XLE',  'Energy'),
    ('XLV',  'Healthcare'),
    ('XLI',  'Industrials'),
    ('XLY',  'Consumer Discretionary'),
    ('XLC',  'Communications'),
    ('XLP',  'Consumer Staples'),
    ('XLRE', 'Real Estate'),
    ('XLU',  'Utilities'),
    ('XLB',  'Materials'),
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def fetch_ssga_holdings(ticker):
    """Download holdings Excel file from SSGA website."""
    url = (f"https://www.ssga.com/us/en/intermediary/library-content/products/"
           f"fund-data/etfs/us/holdings-daily-us-en-{ticker.lower()}.xlsx")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_holdings(excel_bytes):
    """Parse SSGA holdings Excel — tickers start a few rows down."""
    df = pd.read_excel(BytesIO(excel_bytes), header=None)

    # Find the row where the actual holdings data starts
    # SSGA files have metadata at top; look for 'Ticker' or 'Name' column header
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if 'ticker' in vals or 'name' in vals:
            header_row = i
            break

    if header_row is None:
        # Fallback: try row 4 which is common in SSGA files
        header_row = 4

    df = pd.read_excel(BytesIO(excel_bytes), header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Find ticker column
    ticker_col = None
    for col in df.columns:
        if col.lower() in ('ticker', 'symbol', 'sedol'):
            ticker_col = col
            break

    if ticker_col is None:
        return []

    # Find name column
    name_col = None
    for col in df.columns:
        if 'name' in col.lower() or 'holding' in col.lower():
            name_col = col
            break

    # Find weight column
    weight_col = None
    for col in df.columns:
        if 'weight' in col.lower() or '%' in col.lower():
            weight_col = col
            break

    tickers = []
    for _, row in df.iterrows():
        t = str(row[ticker_col]).strip()
        # Skip blanks, cash, headers, footnotes
        if not t or t in ('-', 'nan', 'Ticker', 'TICKER') or len(t) > 8:
            continue
        if any(c in t for c in ['*', '#', '/', ' ']):
            continue

        entry = {'ticker': t}
        if name_col:
            entry['name'] = str(row.get(name_col, '')).strip()
        if weight_col:
            try:
                entry['weight'] = float(row.get(weight_col, 0))
            except (ValueError, TypeError):
                entry['weight'] = 0.0
        tickers.append(entry)

    return tickers


def fetch_via_yfinance(etf_ticker):
    """Fallback: use yfinance to get top holdings."""
    try:
        import yfinance as yf
        t = yf.Ticker(etf_ticker)
        # Try newer yfinance API
        try:
            h = t.get_holdings()
            if h is not None and not h.empty:
                results = []
                for idx, row in h.iterrows():
                    results.append({
                        'ticker': str(idx).strip(),
                        'name':   str(row.get('Name', '')),
                        'weight': float(row.get('% Assets', 0) or 0),
                    })
                return results
        except Exception:
            pass

        # Older yfinance: try funds_data
        try:
            fd = t.funds_data
            if fd and hasattr(fd, 'top_holdings'):
                h = fd.top_holdings
                results = []
                for _, row in h.iterrows():
                    results.append({
                        'ticker': str(row.get('symbol', row.name)).strip(),
                        'name':   str(row.get('holdingName', '')),
                        'weight': float(row.get('holdingPercent', 0) or 0) * 100,
                    })
                return results
        except Exception:
            pass
    except Exception:
        pass
    return []


def save_sector(etf_ticker, sector_name, holdings):
    """Write TradingView watchlist file for this sector."""
    out_file = os.path.join(OUTPUT_DIR, f"{etf_ticker}_{sector_name.replace(' ', '_')}.txt")

    tickers = [h['ticker'] for h in holdings]
    tv_list = ','.join(tickers)

    with open(out_file, 'w') as f:
        f.write(f"# {sector_name} ({etf_ticker})\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# {len(tickers)} holdings\n")
        f.write("#\n")
        f.write("# ── TradingView watchlist (copy line below) ──\n")
        f.write(tv_list + "\n\n")
        f.write("# ── Individual tickers ──\n")
        for h in holdings:
            weight = f"  ({h['weight']:.2f}%)" if h.get('weight') else ''
            name   = f"  {h['name']}"           if h.get('name')   else ''
            f.write(f"{h['ticker']}{weight}{name}\n")

    return out_file, tickers


def main():
    print("=" * 70)
    print("SECTOR ETF HOLDINGS FETCHER")
    print("=" * 70)
    print(f"Output folder: {OUTPUT_DIR}\n")

    all_summary = []

    for etf_ticker, sector_name in SECTOR_ETFS:
        print(f"[{etf_ticker}] {sector_name}... ", end='', flush=True)
        holdings = []

        # Try SSGA first
        try:
            excel = fetch_ssga_holdings(etf_ticker)
            holdings = parse_holdings(excel)
            source = 'SSGA'
        except Exception as e:
            print(f"SSGA failed ({str(e)[:40]}), trying yfinance... ", end='', flush=True)

        # Fallback to yfinance
        if not holdings:
            holdings = fetch_via_yfinance(etf_ticker)
            source = 'yfinance'

        if not holdings:
            print("❌ No data found")
            continue

        out_file, tickers = save_sector(etf_ticker, sector_name, holdings)
        print(f"✓ {len(tickers)} holdings [{source}]")
        all_summary.append((etf_ticker, sector_name, tickers))

    # Write a combined summary file
    summary_file = os.path.join(OUTPUT_DIR, '_ALL_SECTORS_SUMMARY.txt')
    with open(summary_file, 'w') as f:
        f.write(f"ALL SECTOR ETF HOLDINGS\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 70 + "\n\n")
        for etf_ticker, sector_name, tickers in all_summary:
            f.write(f"── {sector_name} ({etf_ticker}) — {len(tickers)} holdings ──\n")
            f.write(','.join(tickers) + "\n\n")

    print(f"\n{'=' * 70}")
    print(f"Done! Files saved to: {OUTPUT_DIR}")
    print(f"Open each .txt file and copy the watchlist line into TradingView.")
    print("=" * 70)


if __name__ == '__main__':
    main()
