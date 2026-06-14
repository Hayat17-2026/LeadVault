from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, jsonify, session
from database.db import get_db

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
@rate_limited
def index():
    db       = get_db()
    role     = session.get("role", "user")
    username = session.get("username", "")

    if role == "user":
        # Personal stats for regular users
        total_earned = db.execute(
            "SELECT COALESCE(SUM(commission_amount),0) FROM lead_referrals WHERE username=? AND status='approved'",
            (username,)
        ).fetchone()[0]
        pending  = db.execute(
            "SELECT COUNT(*) FROM lead_referrals WHERE username=? AND status='pending'", (username,)
        ).fetchone()[0]
        approved = db.execute(
            "SELECT COUNT(*) FROM lead_referrals WHERE username=? AND status='approved'", (username,)
        ).fetchone()[0]
        reviews  = db.execute(
            "SELECT COUNT(*) FROM lead_reviews WHERE username=?", (username,)
        ).fetchone()[0]
        recent_claims = db.execute(
            "SELECT lead_name, status, commission_amount, created_at FROM lead_referrals "
            "WHERE username=? ORDER BY created_at DESC LIMIT 5", (username,)
        ).fetchall()
        recent_reviews = db.execute(
            "SELECT lead_name, rating, comment, created_at FROM lead_reviews "
            "WHERE username=? ORDER BY created_at DESC LIMIT 5", (username,)
        ).fetchall()
        db.close()
        return render_template("dashboard.html",
            user_dashboard=True,
            total_earned=round(float(total_earned), 2),
            pending_claims=pending,
            approved_claims=approved,
            total_reviews=reviews,
            recent_claims=[dict(r) for r in recent_claims],
            recent_reviews=[dict(r) for r in recent_reviews]
        )

    # Admin / Staff — system-wide stats
    total    = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    new      = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    searches = db.execute("SELECT COUNT(*) FROM search_logs").fetchone()[0]
    recent   = db.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT 5").fetchall()
    db.close()
    return render_template("dashboard.html",
        user_dashboard=False,
        total=total, new=new, searches=searches,
        recent=[dict(r) for r in recent]
    )

@dashboard_bp.route("/api/stats")
@login_required
@rate_limited
def api_stats():
    """Real-time stats API for live dashboard charts."""
    db = get_db()

    total     = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    new       = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    contacted = db.execute("SELECT COUNT(*) FROM leads WHERE status='contacted'").fetchone()[0]
    qualified = db.execute("SELECT COUNT(*) FROM leads WHERE status='qualified'").fetchone()[0]
    searches  = db.execute("SELECT COUNT(*) FROM search_logs").fetchone()[0]
    avg_score = db.execute("SELECT AVG(score) FROM leads").fetchone()[0] or 0
    with_email= db.execute("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL AND email != ''").fetchone()[0]

    # Leads by platform
    platform_rows = db.execute(
        "SELECT platform, COUNT(*) as cnt FROM leads GROUP BY platform ORDER BY cnt DESC"
    ).fetchall()
    platforms = {r["platform"] or "unknown": r["cnt"] for r in platform_rows}

    # Score distribution (high/medium/low)
    high   = db.execute("SELECT COUNT(*) FROM leads WHERE score >= 75").fetchone()[0]
    medium = db.execute("SELECT COUNT(*) FROM leads WHERE score >= 50 AND score < 75").fetchone()[0]
    low    = db.execute("SELECT COUNT(*) FROM leads WHERE score < 50").fetchone()[0]

    # Leads per day (last 7 entries grouped by date)
    daily_rows = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM leads GROUP BY DATE(created_at)
        ORDER BY day DESC LIMIT 7
    """).fetchall()
    daily = [{"day": r["day"], "count": r["cnt"]} for r in reversed(daily_rows)]

    # Status breakdown
    status = {"new": new, "contacted": contacted, "qualified": qualified}

    db.close()

    return jsonify({
        "total": total, "new": new, "contacted": contacted, "qualified": qualified,
        "searches": searches, "avg_score": round(avg_score, 1),
        "with_email": with_email,
        "platforms": platforms,
        "score_dist": {"high": high, "medium": medium, "low": low},
        "daily": daily,
        "status": status,
    })
