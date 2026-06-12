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

    conn.commit()
    conn.close()
