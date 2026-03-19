"""
DIVIDEND STOCKS DATABASE
========================
Long-term dividend growth stock list with thesis notes.
Admin can add/edit stocks and write a 5-point thesis for each.
Members can read and browse.
"""

import pymysql
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def init_tables():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dividend_stocks (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                ticker              VARCHAR(20)   NOT NULL UNIQUE,
                company             VARCHAR(200)  NOT NULL,
                sector              VARCHAR(100),
                dividend_yield      DECIMAL(6,2),
                payout_ratio        DECIMAL(6,2),
                years_div_growth    INT,
                target_price        DECIMAL(12,4),
                thesis_moat         TEXT,
                thesis_dividend     TEXT,
                thesis_sustain      TEXT,
                thesis_trend        TEXT,
                thesis_why_now      TEXT,
                display_order       INT DEFAULT 0,
                added_date          DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def get_all_dividend_stocks():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ticker, company, sector, dividend_yield, payout_ratio,
                       years_div_growth, target_price,
                       thesis_moat, thesis_dividend, thesis_sustain,
                       thesis_trend, thesis_why_now, display_order, added_date
                FROM dividend_stocks
                ORDER BY display_order ASC, added_date ASC
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [{
        'id':               r[0],
        'ticker':           r[1],
        'company':          r[2],
        'sector':           r[3] or '',
        'dividend_yield':   float(r[4]) if r[4] else None,
        'payout_ratio':     float(r[5]) if r[5] else None,
        'years_div_growth': r[6],
        'target_price':     float(r[7]) if r[7] else None,
        'thesis_moat':      r[8]  or '',
        'thesis_dividend':  r[9]  or '',
        'thesis_sustain':   r[10] or '',
        'thesis_trend':     r[11] or '',
        'thesis_why_now':   r[12] or '',
        'display_order':    r[13],
        'added_date':       str(r[14])[:10],
    } for r in rows]


def get_dividend_stock(stock_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ticker, company, sector, dividend_yield, payout_ratio,
                       years_div_growth, target_price,
                       thesis_moat, thesis_dividend, thesis_sustain,
                       thesis_trend, thesis_why_now, display_order
                FROM dividend_stocks WHERE id = %s
            """, (stock_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {
        'id':               r[0],
        'ticker':           r[1],
        'company':          r[2],
        'sector':           r[3] or '',
        'dividend_yield':   float(r[4]) if r[4] else None,
        'payout_ratio':     float(r[5]) if r[5] else None,
        'years_div_growth': r[6],
        'target_price':     float(r[7]) if r[7] else None,
        'thesis_moat':      r[8]  or '',
        'thesis_dividend':  r[9]  or '',
        'thesis_sustain':   r[10] or '',
        'thesis_trend':     r[11] or '',
        'thesis_why_now':   r[12] or '',
        'display_order':    r[13],
    }


def upsert_dividend_stock(ticker, company, sector, dividend_yield, payout_ratio,
                          years_div_growth, target_price,
                          thesis_moat, thesis_dividend, thesis_sustain,
                          thesis_trend, thesis_why_now, display_order=0, stock_id=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if stock_id:
                cur.execute("""
                    UPDATE dividend_stocks SET
                        ticker=%s, company=%s, sector=%s,
                        dividend_yield=%s, payout_ratio=%s, years_div_growth=%s,
                        target_price=%s, thesis_moat=%s, thesis_dividend=%s,
                        thesis_sustain=%s, thesis_trend=%s, thesis_why_now=%s,
                        display_order=%s
                    WHERE id=%s
                """, (ticker.upper(), company, sector,
                      dividend_yield or None, payout_ratio or None, years_div_growth or None,
                      target_price or None, thesis_moat, thesis_dividend,
                      thesis_sustain, thesis_trend, thesis_why_now,
                      display_order, stock_id))
            else:
                cur.execute("""
                    INSERT INTO dividend_stocks
                        (ticker, company, sector, dividend_yield, payout_ratio,
                         years_div_growth, target_price, thesis_moat, thesis_dividend,
                         thesis_sustain, thesis_trend, thesis_why_now, display_order, added_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (ticker.upper(), company, sector,
                      dividend_yield or None, payout_ratio or None, years_div_growth or None,
                      target_price or None, thesis_moat, thesis_dividend,
                      thesis_sustain, thesis_trend, thesis_why_now,
                      display_order, datetime.now()))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def delete_dividend_stock(stock_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dividend_stocks WHERE id=%s", (stock_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
