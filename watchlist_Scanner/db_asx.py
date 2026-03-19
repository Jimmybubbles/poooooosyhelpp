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
    'DRO', 'DRR', 'DXS', 'EBO', 'ELD', 'EVN', 'FBU', 'FLT', 'FMG', 'GMG', 'GNC',
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
                image_path   VARCHAR(500),
                bought_date  DATETIME      NOT NULL,
                status       VARCHAR(10)   DEFAULT 'open'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Add image_path if table already existed without it
        try:
            cur.execute("ALTER TABLE asx_picks ADD COLUMN image_path VARCHAR(500)")
        except Exception:
            pass  # Column already exists

        cur.execute("""
            CREATE TABLE IF NOT EXISTS asx_trades (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                ticker      VARCHAR(20)   NOT NULL,
                action      VARCHAR(10)   NOT NULL,
                shares      DECIMAL(12,4) NOT NULL,
                price       DECIMAL(12,4) NOT NULL,
                total       DECIMAL(15,2) NOT NULL,
                pnl         DECIMAL(15,2),
                trade_date  DATETIME      NOT NULL,
                notes       TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Add notes column if table already existed without it
        try:
            cur.execute("ALTER TABLE asx_trades ADD COLUMN notes TEXT")
        except Exception:
            pass  # Column already exists
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


def get_asx_current_price(conn, ticker):
    """Get the latest close price from the asx_prices table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT close FROM asx_prices WHERE ticker = %s ORDER BY date DESC LIMIT 1
        """, (ticker.upper(),))
        row = cur.fetchone()
    return float(row[0]) if row else None


def get_asx_daily_changes(tickers):
    """Return {ticker: (today_close, prev_close)} using last 2 trading days.
    Batch query — one round trip for all tickers."""
    if not tickers:
        return {}
    conn = get_connection()
    result = {}
    try:
        fmt = ','.join(['%s'] * len(tickers))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ticker, close FROM asx_prices
                WHERE ticker IN ({fmt})
                AND date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY ticker, date DESC
            """, list(tickers))
            rows = cur.fetchall()
        grouped = {}
        for ticker, close in rows:
            grouped.setdefault(ticker, []).append(float(close))
        for ticker, closes in grouped.items():
            if len(closes) >= 2:
                result[ticker] = (closes[0], closes[1])
            elif closes:
                result[ticker] = (closes[0], closes[0])
    finally:
        conn.close()
    return result


def get_asx_picks():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, shares, buy_price, target_price,
                   reason, image_path, bought_date
            FROM asx_picks
            WHERE status = 'open'
            ORDER BY bought_date DESC
        """)
        rows = cur.fetchall()

    positions = []
    for r in rows:
        ticker    = r[1]
        shares    = float(r[2])
        buy_price = float(r[3])
        target    = float(r[4]) if r[4] else None
        cur_price = get_asx_current_price(conn, ticker) or buy_price
        cost      = shares * buy_price
        value     = shares * cur_price
        pnl       = value - cost
        pnl_pct   = (pnl / cost * 100) if cost else 0
        positions.append({
            'id':            r[0],
            'ticker':        ticker,
            'shares':        shares,
            'buy_price':     buy_price,
            'target_price':  target,
            'reason':        r[5] or '',
            'image_path':    r[6] or '',
            'bought_date':   str(r[7])[:10],
            'current_price': cur_price,
            'cost':          cost,
            'value':         value,
            'pnl':           pnl,
            'pnl_pct':       pnl_pct,
        })
    conn.close()
    return positions


def get_asx_portfolio_value(positions):
    return sum(p['value'] for p in positions)


def get_asx_history():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, action, shares, price, total, pnl, trade_date, notes
            FROM asx_trades
            ORDER BY trade_date DESC
            LIMIT 200
        """)
        rows = cur.fetchall()
    conn.close()
    return [{
        'id':         r[0],
        'ticker':     r[1],
        'action':     r[2],
        'shares':     float(r[3]),
        'price':      float(r[4]),
        'total':      float(r[5]),
        'pnl':        float(r[6]) if r[6] is not None else None,
        'trade_date': str(r[7])[:16],
        'notes':      r[8] or '',
    } for r in rows]


def buy_asx_stock(ticker, shares, buy_price, target_price, reason, image_filename):
    total_cost = shares * buy_price
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM asx_account WHERE id = 1")
            cash = float(cur.fetchone()[0])
            if total_cost > cash:
                return False, f"Not enough cash. Need A${total_cost:,.2f}, have A${cash:,.2f}"

            cur.execute("UPDATE asx_account SET cash = cash - %s WHERE id = 1", (total_cost,))
            cur.execute("""
                INSERT INTO asx_picks (ticker, shares, buy_price, target_price, reason, image_path, bought_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (ticker.upper(), shares, buy_price, target_price or None, reason, image_filename, datetime.now()))
            pick_id = conn.insert_id()
            cur.execute("""
                INSERT INTO asx_trades (ticker, action, shares, price, total, trade_date, notes)
                VALUES (%s, 'BUY', %s, %s, %s, %s, %s)
            """, (ticker.upper(), shares, buy_price, total_cost, datetime.now(), reason))
        conn.commit()
        return True, pick_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sell_asx_stock(pick_id, sell_price):
    sell_price = float(sell_price)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, shares, buy_price FROM asx_picks
                WHERE id = %s AND status = 'open'
            """, (pick_id,))
            row = cur.fetchone()
            if not row:
                return False, "Position not found"

            ticker, shares, buy_price = row[0], float(row[1]), float(row[2])
            total_value = shares * sell_price
            pnl = total_value - (shares * buy_price)

            cur.execute("UPDATE asx_picks SET status = 'closed' WHERE id = %s", (pick_id,))
            cur.execute("UPDATE asx_account SET cash = cash + %s WHERE id = 1", (total_value,))
            cur.execute("""
                INSERT INTO asx_trades (ticker, action, shares, price, total, pnl, trade_date)
                VALUES (%s, 'SELL', %s, %s, %s, %s, %s)
            """, (ticker, shares, sell_price, total_value, pnl, datetime.now()))
        conn.commit()
        return True, pnl
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
