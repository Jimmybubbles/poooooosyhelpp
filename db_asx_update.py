"""
ASX DAILY PRICE UPDATE
======================
Updates the asx_prices table with the latest daily close data
for all ASX_200 tickers. Run this after ASX market close (~4pm AEST).

Schedule on PythonAnywhere:
    python /path/to/db_asx_update.py

Usage:
    python db_asx_update.py
"""

import yfinance as yf
import pandas as pd
import pymysql
import os
import sys
from datetime import datetime, timedelta, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from db_asx import ASX_200


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def get_last_dates(conn, tickers):
    """Return {ticker: last_date} for all tickers in one query."""
    placeholders = ', '.join(['%s'] * len(tickers))
    sql = f"""
        SELECT ticker, MAX(date) AS last_date
        FROM asx_prices
        WHERE ticker IN ({placeholders})
        GROUP BY ticker
    """
    with conn.cursor() as cur:
        cur.execute(sql, tickers)
        return {row[0]: row[1] for row in cur.fetchall()}


def insert_rows(conn, ticker, df):
    """Insert new OHLCV rows into asx_prices."""
    if df.empty:
        return 0

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.index = pd.to_datetime(df.index).date

    rows = []
    for dt, row in df.iterrows():
        rows.append((
            ticker.upper(),
            str(dt),
            float(row['Open'])   if not pd.isna(row['Open'])   else None,
            float(row['High'])   if not pd.isna(row['High'])   else None,
            float(row['Low'])    if not pd.isna(row['Low'])    else None,
            float(row['Close'])  if not pd.isna(row['Close'])  else None,
            int(row['Volume'])   if not pd.isna(row['Volume']) else None,
        ))

    sql = """
        INSERT INTO asx_prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open   = VALUES(open),
            high   = VALUES(high),
            low    = VALUES(low),
            close  = VALUES(close),
            volume = VALUES(volume)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def main():
    print("=" * 70)
    print("ASX DAILY PRICE UPDATE")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tickers: {len(ASX_200)}")
    print()

    conn = get_connection()
    last_dates = get_last_dates(conn, ASX_200)
    today = date.today()

    up_to_date = 0
    updated    = 0
    new_ticker = 0
    errors     = 0

    for i, ticker in enumerate(ASX_200, 1):
        try:
            last_date = last_dates.get(ticker.upper())

            if last_date is None:
                start = (datetime.now() - timedelta(days=1825)).date()
                print(f"[{i}/{len(ASX_200)}] {ticker}: not in DB, downloading 5 years...")
                new_ticker += 1
            else:
                start = last_date + timedelta(days=1)
                if start >= today:
                    print(f"[{i}/{len(ASX_200)}] {ticker}: up to date")
                    up_to_date += 1
                    continue

            yf_ticker = ticker + '.AX'
            end = today + timedelta(days=1)
            new_data = yf.download(
                yf_ticker,
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
                interval='1d',
                auto_adjust=True,
                progress=False
            )

            if new_data.empty:
                print(f"[{i}/{len(ASX_200)}] {ticker}: no new data")
                continue

            rows = insert_rows(conn, ticker, new_data)
            print(f"[{i}/{len(ASX_200)}] {ticker}: inserted {rows} new rows")
            updated += 1

        except Exception as e:
            print(f"[{i}/{len(ASX_200)}] {ticker}: ERROR - {str(e)[:80]}")
            errors += 1

    conn.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total tickers:   {len(ASX_200)}")
    print(f"Already current: {up_to_date}")
    print(f"Updated:         {updated}")
    print(f"New to DB:       {new_ticker}")
    print(f"Errors:          {errors}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
