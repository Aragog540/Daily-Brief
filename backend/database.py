import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "daily_brief.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            refresh_token TEXT,
            access_token TEXT,
            city TEXT DEFAULT '',
            interests TEXT DEFAULT '',
            delivery_time TEXT DEFAULT '07:00',
            timezone TEXT DEFAULT 'Asia/Kolkata',
            enabled INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def save_user_tokens(email, refresh_token, access_token):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Check if user exists
    cursor.execute("SELECT email FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    if user:
        if refresh_token:
            cursor.execute("""
                UPDATE users 
                SET refresh_token = ?, access_token = ? 
                WHERE email = ?
            """, (refresh_token, access_token, email))
        else:
            cursor.execute("""
                UPDATE users 
                SET access_token = ? 
                WHERE email = ?
            """, (access_token, email))
    else:
        cursor.execute("""
            INSERT INTO users (email, refresh_token, access_token) 
            VALUES (?, ?, ?)
        """, (email, refresh_token or '', access_token))
    conn.commit()
    conn.close()

def update_user_settings(email, city, interests, delivery_time, timezone, enabled):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET city = ?, interests = ?, delivery_time = ?, timezone = ?, enabled = ? 
        WHERE email = ?
    """, (city, interests, delivery_time, timezone, int(enabled), email))
    conn.commit()
    conn.close()

def get_user(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
