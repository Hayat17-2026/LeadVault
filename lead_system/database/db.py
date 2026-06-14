import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            email       TEXT,
            phone       TEXT,
            source_url  TEXT,
            platform    TEXT,
            interests   TEXT,
            score       INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'new',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            query      TEXT,
            platform   TEXT,
            results    INTEGER,
            ran_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT,
            action    TEXT,
            details   TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add notes column if it doesn't exist
    try:
        cur.execute("ALTER TABLE leads ADD COLUMN notes TEXT DEFAULT ''")
    except Exception:
        pass  # column already exists

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lead_reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_url    TEXT NOT NULL,
            lead_name   TEXT,
            username    TEXT NOT NULL,
            rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment     TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lead_referrals (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_url          TEXT NOT NULL,
            lead_name         TEXT,
            username          TEXT NOT NULL,
            status            TEXT DEFAULT 'pending',
            commission_amount REAL DEFAULT 0,
            note              TEXT,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            approved_at       DATETIME
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email         TEXT DEFAULT '',
            full_name     TEXT DEFAULT '',
            role          TEXT DEFAULT 'staff',
            status        TEXT DEFAULT 'active',
            security_q    TEXT DEFAULT 'What is your favorite color?',
            security_a    TEXT DEFAULT '',
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
