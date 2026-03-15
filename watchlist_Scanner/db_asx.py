"""
ASX Database — prices, picks, and trades for Australian stocks.
"""

import pymysql
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

STARTING_BALANCE_AUD = 100_000.0

# ASX 200 tickers (no .AX suffix — stored clean, added when calling yfinance)
ASX_200 = [
    'A2M', 'ABC', 'ABP', 'AGL', 'AIA', 'AIS', 'AKE', 'ALD', 'ALL', 'ALQ',
    'ALU', 'AMC', 'AMP', 'ANN', 'ANZ', 'APA', 'APE', 'ARB', 'ARF', 'ASX',
    'AUB', 'AWC', 'AZJ', 'BEN', 'BGA', 'BHP', 'BOQ', 'BPT', 'BSL', 'BWP',
    'BXB', 'CAR', 'CBA', 'CCP', 'CGF', 'CHC', 'CIA', 'CIP', 'CMW', 'COH',
    'COL', 'CPU', 'CRN', 'CSL', 'CSR', 'CTD', 'CWY', 'DHG', 'DMP', 'DOW',
    'DRR', 'DXS', 'EBO', 'ELD', 'EVN', 'FBU', 'FLT', 'FMG', 'GMG', 'GNC',
    'GOZ', 'GPT', 'GQG', 'GUD', 'GWA', 'HLS', 'HMC', 'HUB', 'HVN', 'IAG',
    'IEL', 'IFL', 'IGO', 'ILU', 'IPH', 'JBH', 'JHG', 'JHX', 'KGN', 'LLC',
    'LNK', 'LOV', 'LTR', 'LYC', 'MCY', 'MGR', 'MIN', 'MMS', 'MND', 'MPL',
    'MQG', 'MTS', 'NAB', 'NCK', 'NCM', 'NEC', 'NHF', 'NST', 'NUF', 'NWL',
    'NXT', 'OFX', 'ORA', 'ORG', 'ORI', 'OZL', 'PDN', 'PLS', 'PME', 'PMV',
    'PPT', 'PRU', 'QAN', 'QBE', 'QUB', 'REA', 'REH', 'RHC', 'RIO', 'RMD',
    'RRL', 'RSG', 'RWC', 'S32', 'SAR', 'SCG', 'SEK', 'SFR', 'SGM', 'SGP',
    'SHL', 'SKC', 'SLC', 'SLR', 'STO', 'SUL', 'SUN', 'SVW', 'TAH', 'TGR',
    'TLS', 'TNE', 'TPG', 'TWE', 'VCX', 'VEA', 'WBC', 'WDS', 'WEB', 'WES',
    'WHC', 'WOR', 'WOW', 'WPR', 'XRO', 'YAL',
]


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS asx_prices (
                id      INT AUTO_INCREMENT PRIMARY KEY,
                ticker  VARCHAR(20)   NOT NULL,
                date    DATE          NOT NULL,
                open    DECIMAL(12,4),
                high    DECIMAL(12,4),
                low     DECIMAL(12,4),
                close   DECIMAL(12,4),
                volume  BIGINT,
                UNIQUE KEY uq_asx (ticker, date),
                INDEX idx_asx_ticker (ticker),
                INDEX idx_asx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS asx_account (
                id   INT PRIMARY KEY DEFAULT 1,
                cash DECIMAL(15,2) NOT NULL DEFAULT 100000.00
            )
        """)
        cur.execute("INSERT IGNORE INTO asx_account (id, cash) VALUES (1, 100000.00)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS asx_picks (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                ticker       VARCHAR(20)   NOT NULL,
                shares       DECIMAL(12,4) NOT NULL,
                buy_price    DECIMAL(12,4) NOT NULL,
                target_price DECIMAL(12,4),
                reason       TEXT,
                bought_date  DATETIME      NOT NULL,
                status       VARCHAR(10)   DEFAULT 'open'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS asx_trades (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                ticker      VARCHAR(20)   NOT NULL,
                action      VARCHAR(10)   NOT NULL,
                shares      DECIMAL(12,4) NOT NULL,
                price       DECIMAL(12,4) NOT NULL,
                total       DECIMAL(15,2) NOT NULL,
                pnl         DECIMAL(15,2),
                trade_date  DATETIME      NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


# ── Price data ────────────────────────────────────────────────────────────────

def get_asx_sparklines_batch(tickers=None):
    """Return {ticker: [last 40 closes]} in one query."""
    conn = get_connection()
    result = {}
    try:
        if tickers is None:
            tickers = ASX_200
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ticker, close FROM asx_prices
                WHERE ticker IN ({fmt})
                ORDER BY ticker, date ASC
            """, tickers)
            for ticker, close in cur.fetchall():
                result.setdefault(ticker, []).append(float(close))
        result = {t: v[-40:] for t, v in result.items()}
    finally:
        conn.close()
    return result


def get_asx_latest_prices(tickers=None):
    """Return {ticker: latest_close}."""
    conn = get_connection()
    result = {}
    try:
        if tickers is None:
            tickers = ASX_200
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT p.ticker, p.close
                FROM asx_prices p
                INNER JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM asx_prices WHERE ticker IN ({fmt})
                    GROUP BY ticker
                ) latest ON p.ticker = latest.ticker AND p.date = latest.max_date
            """, tickers)
            for ticker, close in cur.fetchall():
                result[ticker] = float(close)
    finally:
        conn.close()
    return result


def get_asx_chart_data(ticker):
    """Full OHLCV rows for a ticker, ordered by date."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM asx_prices WHERE ticker = %s ORDER BY date ASC
            """, (ticker,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return rows


def get_tickers_with_data():
    """Return set of ASX tickers that actually have price data in the DB."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM asx_prices")
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


# ── Picks ─────────────────────────────────────────────────────────────────────

def get_asx_account():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT cash FROM asx_account WHERE id = 1")
        row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else STARTING_BALANCE_AUD


def get_asx_picks():
    conn = get_connection()
    latest = get_asx_latest_prices()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, shares, buy_price, target_price, reason, bought_date
            FROM asx_picks WHERE status = 'open' ORDER BY bought_date DESC
        """)
        rows = cur.fetchall()
    conn.close()
    picks = []
    for r in rows:
        current = latest.get(r[1], r[3])
        cost    = float(r[2]) * float(r[3])
        value   = float(r[2]) * float(current)
        picks.append({
            'id': r[0], 'ticker': r[1], 'shares': float(r[2]),
            'buy_price': float(r[3]), 'target_price': float(r[4]) if r[4] else None,
            'reason': r[5] or '', 'bought_date': str(r[6])[:10],
            'current_price': current, 'cost': cost, 'value': value,
            'pnl': value - cost,
        })
    return picks


def get_asx_history():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, action, shares, price, total, pnl, trade_date
            FROM asx_trades ORDER BY trade_date DESC LIMIT 50
        """)
        rows = cur.fetchall()
    conn.close()
    return [{'ticker': r[0], 'action': r[1], 'shares': float(r[2]),
             'price': float(r[3]), 'total': float(r[4]),
             'pnl': float(r[5]) if r[5] is not None else None,
             'trade_date': str(r[6])[:10]} for r in rows]


def get_asx_portfolio_value(picks):
    return sum(p['value'] for p in picks)


def buy_asx_stock(ticker, shares, price, target, reason):
    total = shares * price
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM asx_account WHERE id = 1")
            cash = float(cur.fetchone()[0])
            if total > cash:
                return False, f"Not enough cash (have A${cash:,.2f}, need A${total:,.2f})"
            cur.execute("UPDATE asx_account SET cash = cash - %s WHERE id = 1", (total,))
            cur.execute("""
                INSERT INTO asx_picks (ticker, shares, buy_price, target_price, reason, bought_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (ticker.upper(), shares, price, target or None, reason, datetime.now()))
            pick_id = conn.insert_id()
            cur.execute("""
                INSERT INTO asx_trades (ticker, action, shares, price, total, trade_date)
                VALUES (%s, 'BUY', %s, %s, %s, %s)
            """, (ticker.upper(), shares, price, total, datetime.now()))
        conn.commit()
        return True, pick_id
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def sell_asx_stock(pick_id, sell_price):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker, shares, buy_price FROM asx_picks WHERE id = %s AND status='open'", (pick_id,))
            row = cur.fetchone()
            if not row:
                return False, "Pick not found"
            ticker, shares, buy_price = row[0], float(row[1]), float(row[2])
            total = shares * sell_price
            pnl   = total - shares * buy_price
            cur.execute("UPDATE asx_picks SET status = 'closed' WHERE id = %s", (pick_id,))
            cur.execute("UPDATE asx_account SET cash = cash + %s WHERE id = 1", (total,))
            cur.execute("""
                INSERT INTO asx_trades (ticker, action, shares, price, total, pnl, trade_date)
                VALUES (%s, 'SELL', %s, %s, %s, %s, %s)
            """, (ticker, shares, sell_price, total, pnl, datetime.now()))
        conn.commit()
        return True, pnl
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()
