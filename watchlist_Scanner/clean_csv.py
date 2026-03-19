"""
CLEAN CSV
=========
Removes delisted / dead tickers from CSV/5000.csv by checking
which tickers have no price data in the last 60 days in the DB.

Usage:
    python clean_csv.py           # dry run — shows what would be removed
    python clean_csv.py --apply   # actually rewrites the CSV
"""

import sys
import os
import pymysql
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

CSV_FILE = os.path.join(BASE_DIR, 'CSV', '5000.csv')

# Always keep these regardless of DB data (futures/macro have odd tickers)
ALWAYS_KEEP = {'GC=F', 'SI=F', 'HG=F', 'CL=F', 'DX-Y.NYB', '^TNX'}


def get_active_tickers():
    """Return set of tickers that have at least one row in the last 60 days."""
    conn = pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ticker FROM prices
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
            """)
            return {row[0].upper() for row in cur.fetchall()}
    finally:
        conn.close()


def main():
    apply = '--apply' in sys.argv

    # Read CSV
    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    print(f"CSV has {len(rows)} tickers")

    active = get_active_tickers()
    print(f"DB has {len(active)} tickers with data in last 60 days\n")

    keep = []
    removed = []
    no_data = []

    for row in rows:
        if not row:
            continue
        ticker = row[0].strip().upper()
        if ticker in ALWAYS_KEEP:
            keep.append(row)
        elif ticker in active:
            keep.append(row)
        else:
            removed.append(ticker)

    # Split into: never in DB vs stale
    print(f"Tickers to remove ({len(removed)}):")
    for t in sorted(removed):
        print(f"  {t}")

    print(f"\nWill keep: {len(keep)} tickers")

    if not apply:
        print("\nDry run — no changes made. Run with --apply to rewrite the CSV.")
        return

    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(keep)

    print(f"\nCSV rewritten: {len(removed)} delisted tickers removed.")


if __name__ == '__main__':
    main()
