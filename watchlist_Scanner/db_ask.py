"""
Ask Jimmy — User Q&A Database operations
=========================================
Users register/login, submit ticker + question.
Jimmy (admin) answers from the same page.
"""

import pymysql
import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

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
            CREATE TABLE IF NOT EXISTS ask_users (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                username     VARCHAR(50)  NOT NULL UNIQUE,
                email        VARCHAR(200),
                password_hash VARCHAR(256) NOT NULL,
                created_date DATETIME     NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ask_questions (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                user_id      INT          NOT NULL,
                username     VARCHAR(50)  NOT NULL,
                ticker       VARCHAR(20)  NOT NULL,
                question     TEXT         NOT NULL,
                answer       TEXT,
                created_date DATETIME     NOT NULL,
                answered_date DATETIME,
                status       VARCHAR(20)  DEFAULT 'pending'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    conn.close()


def register_user(username, email, password):
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM ask_users WHERE username = %s", (username,))
            if cur.fetchone():
                return False, "Username already taken."
            pw_hash = generate_password_hash(password)
            cur.execute("""
                INSERT INTO ask_users (username, email, password_hash, created_date)
                VALUES (%s, %s, %s, %s)
            """, (username, email, pw_hash, datetime.now()))
            user_id = conn.insert_id()
        conn.commit()
        return True, user_id
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def login_user(username, password):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM ask_users WHERE username = %s", (username,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return False, "Username not found."
    if not check_password_hash(row[1], password):
        return False, "Wrong password."
    return True, row[0]


def submit_question(user_id, username, ticker, question):
    if not ticker or not question:
        return False, "Ticker and question are required."
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ask_questions (user_id, username, ticker, question, created_date, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
            """, (user_id, username, ticker.upper(), question, datetime.now()))
            qid = conn.insert_id()
        conn.commit()
        return True, qid
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def answer_question(question_id, answer):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ask_questions
                SET answer = %s, answered_date = %s, status = 'answered'
                WHERE id = %s
            """, (answer, datetime.now(), question_id))
        conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def get_questions(user_id=None, admin=False):
    conn = get_connection()
    with conn.cursor() as cur:
        if admin:
            cur.execute("""
                SELECT id, user_id, username, ticker, question, answer,
                       created_date, answered_date, status
                FROM ask_questions ORDER BY created_date DESC
            """)
        elif user_id:
            # Answered questions + this user's pending ones
            cur.execute("""
                SELECT id, user_id, username, ticker, question, answer,
                       created_date, answered_date, status
                FROM ask_questions
                WHERE status = 'answered' OR user_id = %s
                ORDER BY created_date DESC
            """, (user_id,))
        else:
            # Public: answered only
            cur.execute("""
                SELECT id, user_id, username, ticker, question, answer,
                       created_date, answered_date, status
                FROM ask_questions
                WHERE status = 'answered'
                ORDER BY answered_date DESC
            """)
        rows = cur.fetchall()
    conn.close()
    return [{
        'id':            r[0],
        'user_id':       r[1],
        'username':      r[2],
        'ticker':        r[3],
        'question':      r[4],
        'answer':        r[5] or '',
        'created_date':  str(r[6])[:16],
        'answered_date': str(r[7])[:16] if r[7] else '',
        'status':        r[8],
    } for r in rows]


def get_username(user_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT username FROM ask_users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None
