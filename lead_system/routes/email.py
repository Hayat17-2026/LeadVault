from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, request, jsonify
from services.email_service import (
    send_welcome_to_lead, send_lead_added_confirmation, send_report_to_admin
)
from database.db import get_db
from services.activity_service import log_activity

email_bp = Blueprint("email", __name__)

@email_bp.route("/", methods=["GET"])
@login_required
@rate_limited
def email_page():
    return render_template("email.html")

@email_bp.route("/send-welcome", methods=["POST"])
@login_required
@rate_limited
def send_welcome():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip()
    name  = (d.get("name") or "there").strip()
    if not email:
        return jsonify({"status": "error", "message": "No email provided"}), 400
    result = send_welcome_to_lead(email, name)
    if result["status"]=="ok": log_activity("email", f"Sent welcome to {email}")
    return jsonify(result)

@email_bp.route("/send-report", methods=["POST"])
@login_required
@rate_limited
def send_report():
    d = request.get_json(force=True)
    admin_email = (d.get("email") or "").strip()
    if not admin_email:
        return jsonify({"status": "error", "message": "No email provided"}), 400

    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    new   = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    avg   = db.execute("SELECT AVG(score) FROM leads").fetchone()[0] or 0
    db.close()

    result = send_report_to_admin(admin_email, total, new, round(avg, 1))
    return jsonify(result)


@email_bp.route("/send-bulk", methods=["POST"])
@login_required
@rate_limited
def send_bulk():
    """Send welcome email to ALL leads in database that have an email."""
    from services.email_service import send_welcome_to_lead
    import time as _t

    db = get_db()
    leads = [dict(r) for r in db.execute(
        "SELECT * FROM leads WHERE email IS NOT NULL AND email != ''"
    ).fetchall()]
    db.close()

    if not leads:
        return jsonify({"status": "error", "message": "No leads with emails found"}), 400

    sent, failed = 0, 0
    errors = []
    for lead in leads:
        result = send_welcome_to_lead(lead["email"], lead.get("name", "there"))
        if result["status"] == "ok":
            sent += 1
        else:
            failed += 1
            errors.append(result["message"])
        _t.sleep(0.5)   # polite delay between sends

    log_activity("bulk_email", f"Bulk sent to {sent} leads")
    return jsonify({
        "status": "ok",
        "sent": sent, "failed": failed,
        "total": len(leads),
        "error_sample": errors[0] if errors else None
    })
