from database.db import get_db
from flask import session

def log_activity(action: str, details: str = ""):
    """Record an activity in the log."""
    try:
        user = session.get("username", "system")
        db = get_db()
        db.execute(
            "INSERT INTO activity_logs (username, action, details) VALUES (?, ?, ?)",
            (user, action, details)
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[activity] log error: {e}")

def get_recent_activity(limit: int = 50):
    """Get recent activity log entries."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
