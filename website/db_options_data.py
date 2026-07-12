"""
Real Options Chain Data — Database operations
================================================
Pulls real live options chains (yfinance) for tickers actually used on the
options pages (open Options Picks positions + active Options Trackers) and
keeps a rolling 10-day window of daily snapshots. yfinance only exposes
today's live chain — there's no historical options data to backfill, so
this log only starts accumulating from the day it's first run.

Used by Options Picks / Options Tracker as the preferred price source,
falling back to the Black-Scholes model (bs_pricing.py) when no real quote
is available for a given ticker/expiry/strike.
"""

import os
import sys
from datetime import date, timedelta

import pymysql

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

SNAPSHOT_RETENTION_DAYS = 10
STRIKES_PER_SIDE = 6  # nearest N strikes to spot, each of calls/puts


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_chain_snapshots (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                ticker         VARCHAR(20)   NOT NULL,
                snapshot_date  DATE          NOT NULL,
                expiry_date    DATE          NOT NULL,
                option_type    VARCHAR(4)    NOT NULL,
                strike         DECIMAL(12,4) NOT NULL,
                last_price     DECIMAL(12,4),
                bid            DECIMAL(12,4),
                ask            DECIMAL(12,4),
                implied_vol    DECIMAL(8,4),
                volume         INT,
                open_interest  INT,
                in_the_money   TINYINT(1),
                UNIQUE KEY uniq_snap (ticker, snapshot_date, expiry_date, option_type, strike)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def get_relevant_tickers_and_expiries(conn):
    """(ticker, expiry_date) pairs from open Options Picks positions + Options Trackers."""
    pairs = set()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker, expiry_date FROM options_picks WHERE status = 'open'")
        pairs.update(cur.fetchall())
        cur.execute("SELECT DISTINCT ticker, expiry_date FROM options_trackers")
        pairs.update(cur.fetchall())
    return list(pairs)


def _get_spot_and_market(conn, ticker):
    """Returns (spot, market) where market is 'US' or 'ASX' — determines which table
    matched, since options_picks/options_trackers don't track market separately."""
    with conn.cursor() as cur:
        cur.execute("SELECT close FROM prices WHERE ticker = %s ORDER BY date DESC LIMIT 1", (ticker,))
        row = cur.fetchone()
        if row:
            return float(row[0]), 'US'
    with conn.cursor() as cur:
        cur.execute("SELECT close FROM asx_prices WHERE ticker = %s ORDER BY date DESC LIMIT 1", (ticker,))
        row = cur.fetchone()
        if row:
            return float(row[0]), 'ASX'
    return None, None


def refresh_options_chain(conn, ticker, target_expiry, log=None):
    """Fetch the real chain nearest target_expiry and upsert today's snapshot for it."""
    import yfinance as yf

    def _log(msg):
        if log:
            log(msg)

    spot, market = _get_spot_and_market(conn, ticker)
    if spot is None:
        _log(f"  {ticker}: no spot price in DB, skipping\n")
        return 0
    if market == 'ASX':
        # yfinance's US options endpoint isn't reliable for ASX-listed names, and a bare
        # ticker symbol risks silently matching an unrelated US-listed company — skip.
        _log(f"  {ticker}: ASX-listed, real options data not available — using modeled pricing\n")
        return 0

    t = yf.Ticker(ticker)
    try:
        expirations = t.options
    except Exception as e:
        _log(f"  {ticker}: could not fetch expirations — {e}\n")
        return 0

    if not expirations:
        _log(f"  {ticker}: no listed options\n")
        return 0

    target = target_expiry if isinstance(target_expiry, date) else date.fromisoformat(str(target_expiry))
    nearest = min(expirations, key=lambda d: abs((date.fromisoformat(d) - target).days))

    try:
        chain = t.option_chain(nearest)
    except Exception as e:
        _log(f"  {ticker}: could not fetch chain for {nearest} — {e}\n")
        return 0

    today = date.today()
    rows = []
    for option_type, df in (('CALL', chain.calls), ('PUT', chain.puts)):
        if df is None or df.empty:
            continue
        df = df.copy()
        df['dist'] = (df['strike'] - spot).abs()
        nearest_strikes = df.nsmallest(STRIKES_PER_SIDE, 'dist')
        for _, r in nearest_strikes.iterrows():
            rows.append((
                ticker.upper(), today, nearest, option_type, float(r['strike']),
                float(r['lastPrice']) if not _isnan(r.get('lastPrice')) else None,
                float(r['bid']) if not _isnan(r.get('bid')) else None,
                float(r['ask']) if not _isnan(r.get('ask')) else None,
                float(r['impliedVolatility']) if not _isnan(r.get('impliedVolatility')) else None,
                int(r['volume']) if not _isnan(r.get('volume')) else None,
                int(r['openInterest']) if not _isnan(r.get('openInterest')) else None,
                1 if bool(r.get('inTheMoney')) else 0,
            ))

    if not rows:
        _log(f"  {ticker}: chain for {nearest} had no usable rows\n")
        return 0

    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO options_chain_snapshots
                (ticker, snapshot_date, expiry_date, option_type, strike, last_price,
                 bid, ask, implied_vol, volume, open_interest, in_the_money)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                last_price = VALUES(last_price), bid = VALUES(bid), ask = VALUES(ask),
                implied_vol = VALUES(implied_vol), volume = VALUES(volume),
                open_interest = VALUES(open_interest), in_the_money = VALUES(in_the_money)
        """, rows)
    conn.commit()
    _log(f"  {ticker}: snapshotted {len(rows)} contracts (expiry {nearest})\n")
    return len(rows)


def _isnan(v):
    try:
        return v is None or v != v  # NaN != NaN
    except Exception:
        return True


def prune_old_snapshots(conn):
    cutoff = date.today() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM options_chain_snapshots WHERE snapshot_date < %s", (cutoff,))
    conn.commit()


EXPIRY_MATCH_TOLERANCE_DAYS = 5  # how far the real listed expiry may drift from the target


def get_real_quote(ticker, expiry_date, option_type, strike, max_strike_distance=0.01, snapshot_date=None):
    """Real snapshot for this ticker/expiry/strike, if any exists. The snapshot's actual
    listed expiry must fall within EXPIRY_MATCH_TOLERANCE_DAYS of expiry_date — otherwise
    we'd risk silently substituting a quote for a materially different expiration. Defaults
    to the most recent snapshot; pass snapshot_date to look up one specific day (e.g. for a
    tracker's day-by-day table)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if snapshot_date:
                cur.execute("""
                    SELECT last_price, bid, ask, implied_vol, snapshot_date, expiry_date
                    FROM options_chain_snapshots
                    WHERE ticker = %s AND option_type = %s AND ABS(strike - %s) < %s
                          AND snapshot_date = %s AND ABS(DATEDIFF(expiry_date, %s)) <= %s
                    LIMIT 1
                """, (ticker.upper(), option_type.upper(), strike, max_strike_distance,
                      snapshot_date, expiry_date, EXPIRY_MATCH_TOLERANCE_DAYS))
            else:
                cur.execute("""
                    SELECT last_price, bid, ask, implied_vol, snapshot_date, expiry_date
                    FROM options_chain_snapshots
                    WHERE ticker = %s AND option_type = %s AND ABS(strike - %s) < %s
                          AND ABS(DATEDIFF(expiry_date, %s)) <= %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (ticker.upper(), option_type.upper(), strike, max_strike_distance,
                      expiry_date, EXPIRY_MATCH_TOLERANCE_DAYS))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    last_price, bid, ask, iv, snap_date, exp_date = row
    price = None
    if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
        price = (float(bid) + float(ask)) / 2.0
    elif last_price is not None:
        price = float(last_price)
    if price is None:
        return None
    return {
        'price': price, 'bid': float(bid) if bid is not None else None,
        'ask': float(ask) if ask is not None else None,
        'implied_vol': float(iv) if iv is not None else None,
        'snapshot_date': str(snap_date), 'real_expiry_date': str(exp_date),
    }


def get_chain_snapshot(ticker, expiry_date=None):
    """Latest snapshot rows for a ticker (optionally filtered to one expiry), for display."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if expiry_date:
                cur.execute("""
                    SELECT snapshot_date, expiry_date, option_type, strike, last_price,
                           bid, ask, implied_vol, volume, open_interest, in_the_money
                    FROM options_chain_snapshots
                    WHERE ticker = %s AND expiry_date = %s
                    ORDER BY snapshot_date DESC, option_type, strike
                """, (ticker.upper(), expiry_date))
            else:
                cur.execute("""
                    SELECT snapshot_date, expiry_date, option_type, strike, last_price,
                           bid, ask, implied_vol, volume, open_interest, in_the_money
                    FROM options_chain_snapshots
                    WHERE ticker = %s
                    ORDER BY snapshot_date DESC, option_type, strike
                """, (ticker.upper(),))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{
        'snapshot_date': str(r[0]), 'expiry_date': str(r[1]), 'option_type': r[2],
        'strike': float(r[3]), 'last_price': float(r[4]) if r[4] is not None else None,
        'bid': float(r[5]) if r[5] is not None else None, 'ask': float(r[6]) if r[6] is not None else None,
        'implied_vol': float(r[7]) if r[7] is not None else None,
        'volume': int(r[8]) if r[8] is not None else None,
        'open_interest': int(r[9]) if r[9] is not None else None,
        'in_the_money': bool(r[10]),
    } for r in rows]


def refresh_all_relevant_chains(log=None):
    """Entry point called from the price-refresh job: pull real chains for every
    ticker/expiry currently in use on the options pages, then prune old snapshots."""
    def _log(msg):
        if log:
            log(msg)

    conn = get_connection()
    try:
        pairs = get_relevant_tickers_and_expiries(conn)
        if not pairs:
            _log("  No open options positions or trackers — nothing to fetch.\n")
            return
        for ticker, expiry_date in pairs:
            try:
                refresh_options_chain(conn, ticker, expiry_date, log=log)
            except Exception as e:
                _log(f"  {ticker}: ERROR — {e}\n")
        prune_old_snapshots(conn)
    finally:
        conn.close()
