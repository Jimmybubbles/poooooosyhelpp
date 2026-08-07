"""
Jimmy's Ideas — Database operations
====================================
Tracks trade ideas Jimmy posts publicly, one per ticker, tagged to one of
the same 3 trading-style "systems" already used on Jimmy's Picks (see
db_picks.STYLES): swing pullback / range breakout / long-term.

Unlike Jimmy's Picks (a single shared $100k paper portfolio), each idea
here is sized as its own independent $10,000 hypothetical buy-in — there's
no shared cash pool, no position sizing decision. The point isn't "manage
a portfolio", it's "show what your P&L would have been if you'd put $10k
into this specific call when I posted it". Ideas can be closed later with
a locked-in realized P&L, same open/closed pattern as Jimmy's Picks.
"""

import pymysql
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from db_picks import STYLES, get_current_price, get_daily_changes, UPLOADS_DIR  # noqa: F401 (re-exported)

IDEA_NOTIONAL = 10_000.0


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jimmy_ideas (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                ticker       VARCHAR(20)    NOT NULL,
                style        VARCHAR(30)    NOT NULL DEFAULT 'swing_pullback',
                notional     DECIMAL(12,2)  NOT NULL DEFAULT 10000.00,
                shares       DECIMAL(14,6)  NOT NULL,
                buy_price    DECIMAL(12,4)  NOT NULL,
                reason       TEXT,
                image_path   VARCHAR(500),
                posted_date  DATETIME       NOT NULL,
                status       VARCHAR(10)    DEFAULT 'open',
                sell_price   DECIMAL(12,4),
                sell_date    DATETIME,
                sell_reason  TEXT,
                sell_image   VARCHAR(500),
                pnl          DECIMAL(15,2)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def post_idea(ticker, buy_price, style, reason, image_filename, notional=IDEA_NOTIONAL):
    ticker    = ticker.upper().strip()
    buy_price = float(buy_price)
    if not ticker:
        return False, "Ticker is required"
    if buy_price <= 0:
        return False, "Buy price must be positive"

    shares = notional / buy_price
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jimmy_ideas (ticker, style, notional, shares, buy_price, reason, image_path, posted_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (ticker, style if style in STYLES else 'swing_pullback', notional, shares, buy_price,
                  reason, image_filename, datetime.now()))
            idea_id = conn.insert_id()
        conn.commit()
        return True, idea_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_open_ideas(style=None):
    conn = get_connection()
    with conn.cursor() as cur:
        if style:
            cur.execute("""
                SELECT id, ticker, style, notional, shares, buy_price, reason, image_path, posted_date
                FROM jimmy_ideas WHERE status = 'open' AND style = %s ORDER BY posted_date DESC
            """, (style,))
        else:
            cur.execute("""
                SELECT id, ticker, style, notional, shares, buy_price, reason, image_path, posted_date
                FROM jimmy_ideas WHERE status = 'open' ORDER BY posted_date DESC
            """)
        rows = cur.fetchall()

    ideas = []
    for r in rows:
        ticker    = r[1]
        notional  = float(r[3])
        shares    = float(r[4])
        buy_price = float(r[5])
        cur_price = get_current_price(conn, ticker) or buy_price
        value     = shares * cur_price
        pnl       = value - notional
        pnl_pct   = (pnl / notional * 100) if notional else 0
        ideas.append({
            'id':            r[0],
            'ticker':        ticker,
            'style':         r[2],
            'notional':      notional,
            'shares':        shares,
            'buy_price':     buy_price,
            'reason':        r[6] or '',
            'image_path':    r[7] or '',
            'posted_date':   str(r[8])[:10],
            'current_price': cur_price,
            'value':         value,
            'pnl':           pnl,
            'pnl_pct':       pnl_pct,
        })
    conn.close()
    return ideas


def get_closed_ideas(style=None):
    conn = get_connection()
    with conn.cursor() as cur:
        if style:
            cur.execute("""
                SELECT id, ticker, style, notional, shares, buy_price, reason, image_path,
                       posted_date, sell_price, sell_date, sell_reason, sell_image, pnl
                FROM jimmy_ideas WHERE status = 'closed' AND style = %s ORDER BY sell_date DESC
            """, (style,))
        else:
            cur.execute("""
                SELECT id, ticker, style, notional, shares, buy_price, reason, image_path,
                       posted_date, sell_price, sell_date, sell_reason, sell_image, pnl
                FROM jimmy_ideas WHERE status = 'closed' ORDER BY sell_date DESC
            """)
        rows = cur.fetchall()
    conn.close()

    ideas = []
    for r in rows:
        notional = float(r[3])
        pnl      = float(r[13]) if r[13] is not None else 0.0
        pnl_pct  = (pnl / notional * 100) if notional else 0
        ideas.append({
            'id':          r[0],
            'ticker':      r[1],
            'style':       r[2],
            'notional':    notional,
            'shares':      float(r[4]),
            'buy_price':   float(r[5]),
            'reason':      r[6] or '',
            'image_path':  r[7] or '',
            'posted_date': str(r[8])[:10],
            'sell_price':  float(r[9]) if r[9] else 0,
            'sell_date':   str(r[10])[:10] if r[10] else '',
            'sell_reason': r[11] or '',
            'sell_image':  r[12] or '',
            'pnl':         pnl,
            'pnl_pct':     pnl_pct,
        })
    return ideas


def close_idea(idea_id, sell_price, sell_reason='', sell_image=''):
    sell_price = float(sell_price)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT shares, notional FROM jimmy_ideas WHERE id = %s AND status = 'open'
            """, (idea_id,))
            row = cur.fetchone()
            if not row:
                return False, "Idea not found (already closed?)"
            shares, notional = float(row[0]), float(row[1])
            pnl = shares * sell_price - notional
            cur.execute("""
                UPDATE jimmy_ideas
                SET status = 'closed', sell_price = %s, sell_date = %s,
                    sell_reason = %s, sell_image = %s, pnl = %s
                WHERE id = %s
            """, (sell_price, datetime.now(), sell_reason or None, sell_image or None, pnl, idea_id))
        conn.commit()
        return True, pnl
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def delete_idea(idea_id):
    """Remove an idea entirely (admin cleanup — e.g. a posting mistake)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jimmy_ideas WHERE id = %s", (idea_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_system_summary():
    """
    Per-style ("system") track record: open/closed counts, win rate on
    closed ideas, and total P&L split into realized (closed) and
    unrealized (still-open, marked at the current price).
    """
    summary = {key: {
        'label': label, 'open': 0, 'closed': 0, 'wins': 0,
        'realized_pnl': 0.0, 'unrealized_pnl': 0.0, 'total_pnl': 0.0, 'win_rate': None,
    } for key, label in STYLES.items()}

    for idea in get_open_ideas():
        s = summary.get(idea['style'])
        if s is None:
            continue
        s['open'] += 1
        s['unrealized_pnl'] += idea['pnl']

    for idea in get_closed_ideas():
        s = summary.get(idea['style'])
        if s is None:
            continue
        s['closed'] += 1
        s['realized_pnl'] += idea['pnl']
        if idea['pnl'] >= 0:
            s['wins'] += 1

    for s in summary.values():
        s['total_pnl'] = s['realized_pnl'] + s['unrealized_pnl']
        if s['closed']:
            s['win_rate'] = s['wins'] / s['closed'] * 100

    return summary


if __name__ == '__main__':
    init_tables()
    print("jimmy_ideas table ready.")
