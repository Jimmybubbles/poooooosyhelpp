"""
DB INITIAL DOWNLOAD
===================
Downloads 5 years of daily OHLCV data for all tickers in 5000.csv
and writes them into the MySQL database on PythonAnywhere.

Run this ONCE to populate the database for the first time.
After this, use db_daily_update.py to keep it current each day.

Usage:
    python db_initial_download.py
"""

import yfinance as yf
import pandas as pd
import pymysql
import os
from datetime import datetime, timedelta

# Import credentials from config file
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

# Path to ticker list
TICKER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CSV', '5000.csv')

# 5 years of history
START_DATE = (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        charset='utf8mb4'
    )


def create_table(conn):
    """Create the prices table if it doesn't exist."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                ticker      VARCHAR(20)    NOT NULL,
                date        DATE           NOT NULL,
                open        DECIMAL(12,4),
                high        DECIMAL(12,4),
                low         DECIMAL(12,4),
                close       DECIMAL(12,4),
                volume      BIGINT,
                UNIQUE KEY unique_ticker_date (ticker, date),
                INDEX idx_ticker (ticker),
                INDEX idx_date  (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
    conn.commit()
    print("Table 'prices' ready.")


def insert_dataframe(conn, ticker, df):
    """Insert a dataframe of OHLCV rows for a ticker into the database."""
    if df.empty:
        return 0

    # Flatten multi-index columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Make sure we only work with the columns we need
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()

    # Convert index to plain date strings
    df.index = pd.to_datetime(df.index).date

    rows = []
    for date, row in df.iterrows():
        rows.append((
            ticker.upper(),
            str(date),
            float(row['Open'])   if not pd.isna(row['Open'])   else None,
            float(row['High'])   if not pd.isna(row['High'])   else None,
            float(row['Low'])    if not pd.isna(row['Low'])    else None,
            float(row['Close'])  if not pd.isna(row['Close'])  else None,
            int(row['Volume'])   if not pd.isna(row['Volume']) else None,
        ))

    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open   = VALUES(open),
            high   = VALUES(high),
            low    = VALUES(low),
            close  = VALUES(close),
            volume = VALUES(volume)
    """

    with conn.cursor() as cursor:
        cursor.executemany(sql, rows)
    conn.commit()
    return len(rows)


def main():
    print("=" * 70)
    print("DB INITIAL DOWNLOAD")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print()

    # Read ticker list
    tickers_df = pd.read_csv(TICKER_FILE)
    if 'Ticker' in tickers_df.columns:
        tickers = tickers_df['Ticker'].tolist()
    else:
        tickers = tickers_df.iloc[:, 0].tolist()

    print(f"Tickers to download: {len(tickers)}")
    print()

    # Connect and prepare table
    conn = get_connection()
    create_table(conn)

    success = 0
    failed = 0
    failed_tickers = []

    for i, ticker in enumerate(tickers, 1):
        try:
            data = yf.download(
                ticker,
                start=START_DATE,
                end=END_DATE,
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if data.empty:
                print(f"[{i}/{len(tickers)}] {ticker}: no data returned")
                failed += 1
                failed_tickers.append(ticker)
                continue

            rows_inserted = insert_dataframe(conn, ticker, data)
            print(f"[{i}/{len(tickers)}] {ticker}: {rows_inserted} rows inserted")
            success += 1

        except Exception as e:
            print(f"[{i}/{len(tickers)}] {ticker}: ERROR - {str(e)[:60]}")
            failed += 1
            failed_tickers.append(ticker)

        # Reconnect every 500 tickers to avoid timeout
        if i % 500 == 0:
            conn.close()
            conn = get_connection()
            print(f"\n--- Reconnected to DB at ticker {i} ---\n")

    conn.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total tickers:  {len(tickers)}")
    print(f"Successful:     {success}")
    print(f"Failed:         {failed}")
    if failed_tickers:
        print(f"Failed tickers: {', '.join(failed_tickers[:20])}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
