"""
FETCH RUSSELL 2000 SMALL CAP HOLDINGS
======================================
Downloads current IWM (iShares Russell 2000) holdings from BlackRock/iShares,
compares against 5000.csv, and appends any new tickers.

Once tickers are in 5000.csv, db_daily_update.py will automatically
download 5 years of price history for them on the next run.

Usage:
    python fetch_russell_holdings.py

Optional - dry run (shows what would be added, doesn't write):
    python fetch_russell_holdings.py --dry-run
"""

import requests
import pandas as pd
import os
import sys
from io import StringIO

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TICKER_FILE = os.path.join(BASE_DIR, 'CSV', '5000.csv')

# iShares Russell 2000 ETF holdings CSV
IWM_URL = (
    "https://www.ishares.com/us/products/239710/"
    "ISHARES-RUSSELL-2000-ETF/1467271812596.ajax"
    "?fileType=csv&fileName=IWM_holdings&dataType=fund"
)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# iShares sector names → GICS-style names used in 5000.csv
SECTOR_MAP = {
    'Health Care':             'Health Care',
    'Financials':              'Financials',
    'Industrials':             'Industrials',
    'Information Technology':  'Information Technology',
    'Consumer Discretionary':  'Consumer Discretionary',
    'Energy':                  'Energy',
    'Materials':               'Materials',
    'Real Estate':             'Real Estate',
    'Communication Services':  'Communication',
    'Communications':          'Communication',
    'Consumer Staples':        'Consumer Staples',
    'Utilities':               'Utilities',
    '-':                       'Small Cap',
}


def load_existing_tickers():
    """Load tickers already in 5000.csv as an uppercase set."""
    df = pd.read_csv(TICKER_FILE)
    col = 'Ticker' if 'Ticker' in df.columns else df.columns[0]
    return set(df[col].str.upper().tolist())


def fetch_iwm_holdings():
    """
    Download IWM holdings CSV from iShares and parse it.
    Returns a list of dicts: [{ticker, name, sector}, ...]
    """
    print("Downloading IWM holdings from iShares... ", end='', flush=True)
    resp = requests.get(IWM_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    print("OK")

    raw = resp.text

    # iShares CSVs have ~9 rows of metadata at the top before the actual data.
    # Find the line that contains the column headers (has "Ticker" or "Name").
    lines = raw.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        parts = [p.strip().lower() for p in line.split(',')]
        if 'ticker' in parts and 'name' in parts:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(
            "Could not find header row in IWM CSV. "
            "iShares may have changed their format."
        )

    data_text = '\n'.join(lines[header_idx:])
    df = pd.read_csv(StringIO(data_text))
    df.columns = [c.strip() for c in df.columns]

    # Find column names (iShares uses 'Ticker', 'Name', 'Asset Class', 'Sector')
    ticker_col = next((c for c in df.columns if c.lower() == 'ticker'), None)
    name_col   = next((c for c in df.columns if c.lower() == 'name'),   None)
    class_col  = next((c for c in df.columns if c.lower() == 'asset class'), None)
    sector_col = next((c for c in df.columns if 'sector' in c.lower()), None)

    if not ticker_col:
        raise ValueError(f"No 'Ticker' column found. Columns: {list(df.columns)}")

    holdings = []
    for _, row in df.iterrows():
        ticker = str(row[ticker_col]).strip().upper()

        # Skip blanks, cash, futures, bonds — only want equities
        if not ticker or ticker in ('-', 'NAN', ''):
            continue
        if len(ticker) > 6:
            continue
        if any(c in ticker for c in [' ', '/', '*', '#', '.']):
            continue

        # Skip non-equity asset classes
        asset_class = str(row.get(class_col, '')).strip().lower() if class_col else 'equity'
        if asset_class not in ('equity', 'nan', ''):
            continue

        name = str(row.get(name_col, '')).strip() if name_col else ''
        if name in ('nan', ''):
            name = ticker

        raw_sector = str(row.get(sector_col, '')).strip() if sector_col else ''
        sector = SECTOR_MAP.get(raw_sector, 'Small Cap')

        holdings.append({
            'ticker': ticker,
            'name':   name.upper(),
            'sector': sector,
        })

    return holdings


def append_to_csv(new_tickers, dry_run=False):
    """Append new ticker rows to 5000.csv."""
    if not new_tickers:
        print("Nothing to add — all Russell 2000 tickers already in 5000.csv")
        return

    if dry_run:
        print(f"\nDRY RUN — would add {len(new_tickers)} tickers:")
        for t in new_tickers[:20]:
            print(f"  {t['ticker']:<8}  {t['sector']:<30}  {t['name']}")
        if len(new_tickers) > 20:
            print(f"  ... and {len(new_tickers) - 20} more")
        return

    rows = '\n'.join(
        f"{t['ticker']},{t['name']},{t['sector']}"
        for t in new_tickers
    )
    with open(TICKER_FILE, 'a', encoding='utf-8', newline='') as f:
        f.write('\n' + rows + '\n')

    print(f"\nAdded {len(new_tickers)} new small cap tickers to 5000.csv")
    print("Next time db_daily_update.py runs on PythonAnywhere it will")
    print("automatically download 5 years of history for each new ticker.")


def main():
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("RUSSELL 2000 SMALL CAP HOLDINGS FETCHER")
    print("=" * 60)

    # Load what's already in 5000.csv
    existing = load_existing_tickers()
    print(f"Existing tickers in 5000.csv: {len(existing)}")

    # Fetch IWM holdings
    try:
        holdings = fetch_iwm_holdings()
    except Exception as e:
        print(f"\nERROR fetching IWM: {e}")
        print("\nTrying fallback via yfinance...")
        holdings = fetch_via_yfinance_fallback()

    print(f"IWM holdings fetched: {len(holdings)} equities")

    # Find new tickers not already in 5000.csv
    new_tickers = [h for h in holdings if h['ticker'] not in existing]
    already_have = len(holdings) - len(new_tickers)

    print(f"Already in 5000.csv:  {already_have}")
    print(f"New to add:           {len(new_tickers)}")

    if new_tickers:
        # Show breakdown by sector
        from collections import Counter
        sector_counts = Counter(t['sector'] for t in new_tickers)
        print("\nNew tickers by sector:")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            print(f"  {sector:<35} {count}")

    append_to_csv(new_tickers, dry_run=dry_run)
    print("\nDone.")


def fetch_via_yfinance_fallback():
    """Fallback: use yfinance to get IWM top holdings (limited to ~25)."""
    print("Note: yfinance only returns top ~25 holdings, not the full 2000.")
    try:
        import yfinance as yf
        t = yf.Ticker('IWM')
        holdings = []
        try:
            fd = t.funds_data
            if fd and hasattr(fd, 'top_holdings'):
                for _, row in fd.top_holdings.iterrows():
                    ticker = str(row.get('symbol', row.name)).strip().upper()
                    if ticker and len(ticker) <= 6:
                        holdings.append({
                            'ticker': ticker,
                            'name':   str(row.get('holdingName', ticker)).upper(),
                            'sector': 'Small Cap',
                        })
        except Exception:
            pass
        return holdings
    except Exception as e:
        print(f"yfinance fallback also failed: {e}")
        return []


if __name__ == '__main__':
    main()
