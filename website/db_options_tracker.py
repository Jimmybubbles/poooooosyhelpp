"""
Options Tracker — Database operations
======================================
Auto-priced day-by-day tracker for the cheapest deep-OTM put and call for a
chosen ticker/expiry — e.g. "what does the cheapest NFLX put/call expiring
in 2 weeks do every day until expiry". Priced with Black-Scholes
(bs_pricing.py) against the real underlying close each trading day — there's
no real options market data feed in this app.
"""

import os
import sys
from datetime import datetime, date, timedelta

import pymysql

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from bs_pricing import bs_price_greeks, assumed_iv_for_price, strike_increment_for_price, effective_iv
from db_options_data import get_real_quote

RISK_FREE_RATE = 0.045
CHEAP_FLOOR = 0.10      # $ premium threshold that counts as "cheap"
MAX_STRIKE_STEPS = 60
MAX_MONEYNESS = 0.40    # don't walk further than 40% OTM — real chains don't list strikes that far out


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_trackers (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                ticker       VARCHAR(20)   NOT NULL,
                expiry_date  DATE          NOT NULL,
                put_strike   DECIMAL(12,4) NOT NULL,
                call_strike  DECIMAL(12,4) NOT NULL,
                assumed_iv   DECIMAL(6,4)  NOT NULL,
                created_date DATE          NOT NULL,
                status       VARCHAR(10)   DEFAULT 'active'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def get_current_price(conn, ticker):
    with conn.cursor() as cur:
        cur.execute("SELECT close FROM prices WHERE ticker = %s ORDER BY date DESC LIMIT 1", (ticker.upper(),))
        row = cur.fetchone()
    return float(row[0]) if row else None


def _find_cheap_strike(spot, dte_days, iv, kind):
    """Walk strikes away from ATM until the Black-Scholes price drops to the cheap floor
    (or the strike ladder runs out of realistic room — real chains don't list strikes
    arbitrarily far from the money just because a flat-vol model prices them near zero)."""
    increment = strike_increment_for_price(spot)
    strike = round(spot / increment) * increment
    t_years = max(dte_days, 0) / 365.0
    last_strike, last_price = strike, None
    for _ in range(MAX_STRIKE_STEPS):
        strike = strike - increment if kind == 'put' else strike + increment
        if strike <= 0 or abs(strike - spot) / spot > MAX_MONEYNESS:
            break
        skewed_iv = effective_iv(iv, spot, strike)
        price = bs_price_greeks(spot, strike, t_years, skewed_iv, RISK_FREE_RATE, kind)['price']
        last_strike, last_price = strike, price
        if price <= CHEAP_FLOOR:
            break
    return round(last_strike, 2), (round(last_price, 4) if last_price is not None else None)


def create_tracker(ticker, expiry_date_str):
    ticker = ticker.upper().strip()
    conn = get_connection()
    try:
        spot = get_current_price(conn, ticker)
        if spot is None:
            return False, f"No price data for {ticker}"

        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
        created = date.today()
        dte_days = (expiry_date - created).days
        if dte_days <= 0:
            return False, "Expiry date must be in the future"

        iv = assumed_iv_for_price(spot)
        put_strike, _  = _find_cheap_strike(spot, dte_days, iv, 'put')
        call_strike, _ = _find_cheap_strike(spot, dte_days, iv, 'call')

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO options_trackers
                    (ticker, expiry_date, put_strike, call_strike, assumed_iv, created_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (ticker, expiry_date, put_strike, call_strike, iv, created))
            tracker_id = conn.insert_id()
        conn.commit()
        return True, tracker_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_trackers():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ticker, expiry_date, put_strike, call_strike, assumed_iv, created_date, status
            FROM options_trackers
            ORDER BY created_date DESC, id DESC
        """)
        rows = cur.fetchall()
    conn.close()
    return [{
        'id': r[0], 'ticker': r[1], 'expiry_date': r[2], 'put_strike': float(r[3]),
        'call_strike': float(r[4]), 'assumed_iv': float(r[5]), 'created_date': r[6],
        'status': r[7],
    } for r in rows]


def delete_tracker(tracker_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM options_trackers WHERE id = %s", (tracker_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def build_tracker_rows(tracker):
    """Day-by-day put/call price + underlying close from created_date to expiry_date."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date, close FROM prices
            WHERE ticker = %s AND date BETWEEN %s AND %s
            ORDER BY date ASC
        """, (tracker['ticker'], tracker['created_date'], tracker['expiry_date']))
        price_rows = cur.fetchall()
    conn.close()

    closes = {r[0]: float(r[1]) for r in price_rows}
    today = date.today()

    rows = []
    d = tracker['created_date']
    while d <= tracker['expiry_date']:
        if d.weekday() < 5:  # Mon-Fri only
            close = closes.get(d)
            dte_days = (tracker['expiry_date'] - d).days
            put_price = call_price = None
            put_real  = get_real_quote(tracker['ticker'], tracker['expiry_date'], 'PUT',
                                        tracker['put_strike'], snapshot_date=d)
            call_real = get_real_quote(tracker['ticker'], tracker['expiry_date'], 'CALL',
                                        tracker['call_strike'], snapshot_date=d)
            if put_real is not None:
                put_price = put_real['price']
            if call_real is not None:
                call_price = call_real['price']
            if close is not None:
                if put_price is None:
                    put_iv = effective_iv(tracker['assumed_iv'], close, tracker['put_strike'])
                    put_price = bs_price_greeks(close, tracker['put_strike'], max(dte_days, 0) / 365.0,
                                                 put_iv, RISK_FREE_RATE, 'put')['price']
                if call_price is None:
                    call_iv = effective_iv(tracker['assumed_iv'], close, tracker['call_strike'])
                    call_price = bs_price_greeks(close, tracker['call_strike'], max(dte_days, 0) / 365.0,
                                                  call_iv, RISK_FREE_RATE, 'call')['price']
            rows.append({
                'date': d.strftime('%d-%b'), 'close': close,
                'put_price': put_price, 'call_price': call_price,
                'put_real': put_real is not None, 'call_real': call_real is not None,
                'is_today': d == today,
            })
        d += timedelta(days=1)
    return rows
