"""
Options Picks — Database operations
====================================
Dummy $100k options paper-trading account: long calls/puts only. Positions
are marked to market with Black-Scholes (bs_pricing.py) against the real
underlying stock price and real time-to-expiry — there's no options market
data feed in this app, so this is an approximation for education purposes.
"""

import os
import sys
from datetime import datetime, date

import pymysql

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from bs_pricing import bs_price_greeks, assumed_iv_for_price, effective_iv

STARTING_BALANCE = 100_000.0
CONTRACT_SIZE = 100  # shares per contract
RISK_FREE_RATE = 0.045


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_account (
                id   INT PRIMARY KEY DEFAULT 1,
                cash DECIMAL(15,2) NOT NULL DEFAULT 100000.00
            )
        """)
        cur.execute("INSERT IGNORE INTO options_account (id, cash) VALUES (1, 100000.00)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_picks (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                ticker         VARCHAR(20)    NOT NULL,
                option_type    VARCHAR(4)     NOT NULL,
                strike         DECIMAL(12,4)  NOT NULL,
                expiry_date    DATE           NOT NULL,
                contracts      INT            NOT NULL,
                entry_premium  DECIMAL(12,4)  NOT NULL,
                assumed_iv     DECIMAL(6,4)   NOT NULL DEFAULT 0.4000,
                reason         TEXT,
                bought_date    DATETIME       NOT NULL,
                status         VARCHAR(10)    DEFAULT 'open'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_trades (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                ticker         VARCHAR(20)   NOT NULL,
                option_type    VARCHAR(4)    NOT NULL,
                strike         DECIMAL(12,4) NOT NULL,
                expiry_date    DATE          NOT NULL,
                action         VARCHAR(10)   NOT NULL,
                contracts      INT           NOT NULL,
                premium        DECIMAL(12,4) NOT NULL,
                total          DECIMAL(15,2) NOT NULL,
                pnl            DECIMAL(15,2),
                trade_date     DATETIME      NOT NULL,
                notes          TEXT,
                pick_id        INT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def get_options_account():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT cash FROM options_account WHERE id = 1")
        row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else STARTING_BALANCE


def get_current_price(conn, ticker):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT close FROM prices WHERE ticker = %s ORDER BY date DESC LIMIT 1
        """, (ticker.upper(),))
        row = cur.fetchone()
    return float(row[0]) if row else None


def _mark_position(conn, ticker, option_type, strike, expiry_date, entry_premium, contracts, assumed_iv):
    spot = get_current_price(conn, ticker)
    dte_days = (expiry_date - date.today()).days
    kind = 'call' if option_type == 'CALL' else 'put'

    if spot is None:
        # No price data — fall back to entry premium so it doesn't look broken
        cur_premium, delta, theta = entry_premium, None, None
    else:
        iv = effective_iv(assumed_iv, spot, strike)
        g = bs_price_greeks(spot, strike, max(dte_days, 0) / 365.0, iv, RISK_FREE_RATE, kind)
        cur_premium, delta, theta = g['price'], g['delta'], g['theta']

    cost = entry_premium * contracts * CONTRACT_SIZE
    value = cur_premium * contracts * CONTRACT_SIZE
    pnl = value - cost
    pnl_pct = (pnl / cost * 100) if cost else 0

    return {
        'spot': spot, 'dte': max(dte_days, 0), 'expired': dte_days < 0,
        'current_premium': cur_premium, 'delta': delta, 'theta': theta,
        'cost': cost, 'value': value, 'pnl': pnl, 'pnl_pct': pnl_pct,
    }


def get_options_positions():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, option_type, strike, expiry_date, contracts,
                   entry_premium, assumed_iv, reason, bought_date
            FROM options_picks
            WHERE status = 'open'
            ORDER BY bought_date DESC
        """)
        rows = cur.fetchall()

    positions = []
    for r in rows:
        ticker        = r[1]
        option_type   = r[2]
        strike        = float(r[3])
        expiry_date   = r[4]
        contracts     = int(r[5])
        entry_premium = float(r[6])
        assumed_iv    = float(r[7])

        mark = _mark_position(conn, ticker, option_type, strike, expiry_date,
                               entry_premium, contracts, assumed_iv)
        positions.append({
            'id': r[0], 'ticker': ticker, 'option_type': option_type,
            'strike': strike, 'expiry_date': str(expiry_date), 'contracts': contracts,
            'entry_premium': entry_premium, 'assumed_iv': assumed_iv,
            'reason': r[8] or '', 'bought_date': str(r[9])[:10],
            **mark,
        })
    conn.close()
    return positions


def get_options_portfolio_value(positions):
    return sum(p['value'] for p in positions)


def get_options_history():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, option_type, strike, expiry_date, action,
                   contracts, premium, total, pnl, trade_date, notes
            FROM options_trades
            ORDER BY trade_date DESC
            LIMIT 200
        """)
        rows = cur.fetchall()
    conn.close()
    return [{
        'id': r[0], 'ticker': r[1], 'option_type': r[2], 'strike': float(r[3]),
        'expiry_date': str(r[4]), 'action': r[5], 'contracts': int(r[6]),
        'premium': float(r[7]), 'total': float(r[8]),
        'pnl': float(r[9]) if r[9] is not None else None,
        'trade_date': str(r[10])[:16], 'notes': r[11] or '',
    } for r in rows]


def buy_option(ticker, option_type, strike, expiry_date, contracts, entry_premium, assumed_iv, reason):
    """assumed_iv: pass None to auto-derive from the current underlying price."""
    ticker = ticker.upper()
    option_type = option_type.upper()
    strike = float(strike)
    contracts = int(contracts)
    entry_premium = float(entry_premium)
    total_cost = entry_premium * contracts * CONTRACT_SIZE

    conn = get_connection()
    try:
        if assumed_iv is None or assumed_iv == '':
            spot = get_current_price(conn, ticker)
            assumed_iv = assumed_iv_for_price(spot) if spot else 0.40
        else:
            assumed_iv = float(assumed_iv)

        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM options_account WHERE id = 1")
            cash = float(cur.fetchone()[0])
            if total_cost > cash:
                return False, f"Not enough cash. Need ${total_cost:,.2f}, have ${cash:,.2f}"

            cur.execute("UPDATE options_account SET cash = cash - %s WHERE id = 1", (total_cost,))
            cur.execute("""
                INSERT INTO options_picks
                    (ticker, option_type, strike, expiry_date, contracts,
                     entry_premium, assumed_iv, reason, bought_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (ticker, option_type, strike, expiry_date, contracts,
                  entry_premium, assumed_iv, reason, datetime.now()))
            pick_id = conn.insert_id()
            cur.execute("""
                INSERT INTO options_trades
                    (ticker, option_type, strike, expiry_date, action, contracts,
                     premium, total, trade_date, notes, pick_id)
                VALUES (%s, %s, %s, %s, 'BUY', %s, %s, %s, %s, %s, %s)
            """, (ticker, option_type, strike, expiry_date, contracts,
                  entry_premium, total_cost, datetime.now(), reason, pick_id))
        conn.commit()
        return True, pick_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sell_option(pick_id, sell_premium, sell_reason=''):
    sell_premium = float(sell_premium)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, option_type, strike, expiry_date, contracts, entry_premium
                FROM options_picks WHERE id = %s AND status = 'open'
            """, (pick_id,))
            row = cur.fetchone()
            if not row:
                return False, "Position not found"

            ticker, option_type, strike, expiry_date, contracts, entry_premium = row
            contracts = int(contracts)
            entry_premium = float(entry_premium)
            total_value = sell_premium * contracts * CONTRACT_SIZE
            pnl = total_value - (entry_premium * contracts * CONTRACT_SIZE)

            cur.execute("UPDATE options_picks SET status = 'closed' WHERE id = %s", (pick_id,))
            cur.execute("UPDATE options_account SET cash = cash + %s WHERE id = 1", (total_value,))
            cur.execute("""
                INSERT INTO options_trades
                    (ticker, option_type, strike, expiry_date, action, contracts,
                     premium, total, pnl, trade_date, notes, pick_id)
                VALUES (%s, %s, %s, %s, 'SELL', %s, %s, %s, %s, %s, %s, %s)
            """, (ticker, option_type, strike, expiry_date, contracts,
                  sell_premium, total_value, pnl, datetime.now(), sell_reason or None, pick_id))
        conn.commit()
        return True, pnl
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
