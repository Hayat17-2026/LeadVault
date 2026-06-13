from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, request, jsonify, session
from database.db import get_db
from services.activity_service import log_activity

leads_bp = Blueprint("leads", __name__)

@leads_bp.route("/", methods=["GET"])
@login_required
@rate_limited
def leads_page():
    return render_template("leads.html")

@leads_bp.route("/suggestions", methods=["GET"])
@login_required
def suggestions():
    db   = get_db()
    rows = db.execute("SELECT name, email, phone FROM leads ORDER BY name").fetchall()
    db.close()
    return jsonify([{"name": r["name"], "email": r["email"] or "", "phone": r["phone"] or ""} for r in rows])

@leads_bp.route("/all", methods=["GET"])
@login_required
@rate_limited
def get_all():
    db   = get_db()
    rows = db.execute("SELECT * FROM leads ORDER BY score DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@leads_bp.route("/add", methods=["POST"])
@login_required
@rate_limited
def add_lead():
    d  = request.get_json()
    db = get_db()
    db.execute(
        """INSERT INTO leads (name, email, phone, source_url, platform, interests, score)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (d.get("name"), d.get("email"), d.get("phone"),
         d.get("source_url"), d.get("platform"),
         d.get("interests"), d.get("score", 0))
    )
    db.commit()
    db.close()
    log_activity("add_lead", f'Added: {d.get("name","unknown")}')
    return jsonify({"status": "ok", "message": "Lead saved"})

@leads_bp.route("/add-bulk", methods=["POST"])
@login_required
@rate_limited
def add_bulk():
    data    = request.get_json(force=True) or {}
    leads   = data.get("leads", [])
    db      = get_db()
    saved, skipped = 0, 0
    for d in leads:
        try:
            db.execute(
                """INSERT INTO leads (name, email, phone, source_url, platform, interests, score)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (d.get("name"), d.get("email"), d.get("phone"),
                 d.get("source_url"), d.get("platform"),
                 d.get("interests"), d.get("score", 0))
            )
            saved += 1
        except Exception:
            skipped += 1
    db.commit()
    db.close()
    log_activity("add_lead", f"Bulk saved {saved} leads from search results")
    return jsonify({"status": "ok", "saved": saved, "skipped": skipped})

@leads_bp.route("/update-status", methods=["POST"])
@login_required
@rate_limited
def update_status():
    d  = request.get_json()
    db = get_db()
    db.execute("UPDATE leads SET status=? WHERE id=?", (d["status"], d["id"]))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})

@leads_bp.route("/delete/<int:lead_id>", methods=["DELETE"])
@login_required
@rate_limited
def delete_lead(lead_id):
    db = get_db()
    db.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})

@leads_bp.route("/stats", methods=["GET"])
@login_required
@rate_limited
def stats():
    db    = get_db()
    total = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    new   = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    contacted = db.execute("SELECT COUNT(*) FROM leads WHERE status='contacted'").fetchone()[0]
    avg_score = db.execute("SELECT AVG(score) FROM leads").fetchone()[0]
    db.close()
    return jsonify({
        "total": total, "new": new,
        "contacted": contacted,
        "avg_score": round(avg_score or 0, 1)
    })


# ── NEW FEATURE 1: DUPLICATE DETECTION ────────────────────────────────────────
@leads_bp.route("/duplicates", methods=["GET"])
@login_required
@rate_limited
def find_duplicates():
    """Smart duplicate detection — finds leads with same email, phone, or similar name."""
    db   = get_db()
    rows = [dict(r) for r in db.execute("SELECT * FROM leads").fetchall()]
    db.close()

    duplicates = []
    seen_email = {}
    seen_phone = {}

    for lead in rows:
        email = (lead.get("email") or "").strip().lower()
        phone = re_digits(lead.get("phone") or "")

        # Email duplicate
        if email and email != "":
            if email in seen_email:
                duplicates.append({
                    "type": "email", "value": email,
                    "lead1": seen_email[email], "lead2": lead
                })
            else:
                seen_email[email] = lead

        # Phone duplicate
        if phone and len(phone) >= 7:
            if phone in seen_phone:
                duplicates.append({
                    "type": "phone", "value": phone,
                    "lead1": seen_phone[phone], "lead2": lead
                })
            else:
                seen_phone[phone] = lead

    return jsonify({"status": "ok", "count": len(duplicates), "duplicates": duplicates})


@leads_bp.route("/remove-duplicates", methods=["POST"])
@login_required
@rate_limited
def remove_duplicates():
    """Automatically remove duplicate leads, keeping the one with highest score."""
    db   = get_db()
    rows = [dict(r) for r in db.execute("SELECT * FROM leads ORDER BY score DESC").fetchall()]

    seen = set()
    removed = 0
    for lead in rows:
        email = (lead.get("email") or "").strip().lower()
        phone = re_digits(lead.get("phone") or "")
        key = email if email else (phone if phone else None)
        if key:
            if key in seen:
                db.execute("DELETE FROM leads WHERE id=?", (lead["id"],))
                removed += 1
            else:
                seen.add(key)

    db.commit()
    db.close()
    return jsonify({"status": "ok", "removed": removed})


def re_digits(text):
    import re
    return re.sub(r"\D", "", text or "")


# ── NEW FEATURE 2: PDF EXPORT ─────────────────────────────────────────────────
@leads_bp.route("/export-pdf", methods=["GET"])
@login_required
@rate_limited
def export_pdf():
    """Generate and download a professional PDF report of all leads."""
    from flask import send_file
    from services.pdf_service import generate_leads_pdf
    import io

    db    = get_db()
    leads = [dict(r) for r in db.execute("SELECT * FROM leads ORDER BY score DESC").fetchall()]
    total = len(leads)
    new   = sum(1 for l in leads if l.get("status") == "new")
    with_email = sum(1 for l in leads if l.get("email"))
    avg   = round(sum(l.get("score", 0) for l in leads) / total, 1) if total else 0
    db.close()

    stats = {"total": total, "new": new, "with_email": with_email, "avg_score": avg}
    pdf_bytes = generate_leads_pdf(leads, stats)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="LeadAI_Report.pdf"
    )


# ── NEW FEATURE 3: LEAD NOTES ─────────────────────────────────────────────────
@leads_bp.route("/update-notes", methods=["POST"])
@login_required
@rate_limited
def update_notes():
    """Save a note for a lead."""
    d = request.get_json(force=True)
    db = get_db()
    db.execute("UPDATE leads SET notes=? WHERE id=?", (d.get("notes", ""), d["id"]))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ── EDIT LEAD (full update) ───────────────────────────────────────────────────
@leads_bp.route("/edit", methods=["POST"])
@login_required
@rate_limited
def edit_lead():
    """Update any field of a lead."""
    d = request.get_json(force=True)
    lead_id = d.get("id")
    if not lead_id:
        return jsonify({"status": "error", "message": "No lead ID"}), 400
    db = get_db()
    db.execute("""
        UPDATE leads SET name=?, email=?, phone=?, platform=?, interests=?, score=?, status=?
        WHERE id=?
    """, (
        d.get("name", ""), d.get("email", ""), d.get("phone", ""),
        d.get("platform", ""), d.get("interests", ""),
        d.get("score", 0), d.get("status", "new"), lead_id
    ))
    db.commit()
    db.close()
    log_activity("edit_lead", f'Edited lead #{lead_id}: {d.get("name","")}')
    return jsonify({"status": "ok", "message": "Lead updated"})


# ── ADD LEAD MANUALLY ─────────────────────────────────────────────────────────
@leads_bp.route("/add-manual", methods=["POST"])
@login_required
@rate_limited
def add_manual():
    """Manually add a new lead from the database page."""
    d = request.get_json(force=True)
    if not d.get("name"):
        return jsonify({"status": "error", "message": "Name is required"}), 400
    db = get_db()
    db.execute("""
        INSERT INTO leads (name, email, phone, platform, interests, score, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        d.get("name"), d.get("email", ""), d.get("phone", ""),
        d.get("platform", "manual"), d.get("interests", ""),
        d.get("score", 50), "new"
    ))
    db.commit()
    db.close()
    log_activity("add_lead", f'Manually added: {d.get("name")}')
    return jsonify({"status": "ok", "message": "Lead added"})


# ── REVIEWS ──────────────────────────────────────────────────────────────────

@leads_bp.route("/add-review", methods=["POST"])
@login_required
def add_review():
    data      = request.get_json(force=True) or {}
    lead_url  = data.get("lead_url", "").strip()
    lead_name = data.get("lead_name", "").strip()
    rating    = int(data.get("rating", 0))
    comment   = data.get("comment", "").strip()
    username  = session.get("username", "guest")
    if not lead_url or not (1 <= rating <= 5):
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM lead_reviews WHERE lead_url=? AND username=?", (lead_url, username)).fetchone()
    if existing:
        db.execute("UPDATE lead_reviews SET rating=?, comment=?, created_at=CURRENT_TIMESTAMP WHERE id=?", (rating, comment, existing["id"]))
    else:
        db.execute("INSERT INTO lead_reviews (lead_url, lead_name, username, rating, comment) VALUES (?,?,?,?,?)", (lead_url, lead_name, username, rating, comment))
    db.commit(); db.close()
    log_activity("review", f'Reviewed "{lead_name}" — {rating}/5 stars')
    return jsonify({"status": "ok"})

@leads_bp.route("/get-reviews", methods=["GET"])
@login_required
def get_reviews():
    lead_url = request.args.get("url", "")
    username = session.get("username", "guest")
    db   = get_db()
    rows = db.execute("SELECT username, rating, comment, created_at FROM lead_reviews WHERE lead_url=? ORDER BY created_at DESC", (lead_url,)).fetchall()
    agg  = db.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM lead_reviews WHERE lead_url=?", (lead_url,)).fetchone()
    mine = db.execute("SELECT rating, comment FROM lead_reviews WHERE lead_url=? AND username=?", (lead_url, username)).fetchone()
    db.close()
    return jsonify({
        "status": "ok",
        "reviews": [dict(r) for r in rows],
        "avg": round(agg["avg"], 1) if agg["avg"] else None,
        "count": agg["cnt"],
        "my_review": dict(mine) if mine else None
    })

# ── REFERRALS / COMMISSIONS ───────────────────────────────────────────────────

@leads_bp.route("/claim-visit", methods=["POST"])
@login_required
def claim_visit():
    data      = request.get_json(force=True) or {}
    lead_url  = data.get("lead_url", "").strip()
    lead_name = data.get("lead_name", "").strip()
    username  = session.get("username", "guest")
    if not lead_url:
        return jsonify({"status": "error", "message": "No lead URL"}), 400
    db = get_db()
    existing = db.execute("SELECT id, status FROM lead_referrals WHERE lead_url=? AND username=?", (lead_url, username)).fetchone()
    if existing:
        db.close()
        return jsonify({"status": "error", "message": f"Already claimed — status: {existing['status']}"})
    db.execute("INSERT INTO lead_referrals (lead_url, lead_name, username, status) VALUES (?,?,?,'pending')", (lead_url, lead_name, username))
    db.commit(); db.close()
    log_activity("referral", f'Claimed visit to "{lead_name}"')
    return jsonify({"status": "ok", "message": "Visit claimed! Pending admin approval."})

@leads_bp.route("/my-referrals", methods=["GET"])
@login_required
def my_referrals():
    username = session.get("username", "guest")
    db   = get_db()
    rows = db.execute("SELECT * FROM lead_referrals WHERE username=? ORDER BY created_at DESC", (username,)).fetchall()
    total = db.execute("SELECT SUM(commission_amount) as t FROM lead_referrals WHERE username=? AND status='approved'", (username,)).fetchone()["t"] or 0
    db.close()
    return jsonify({"status": "ok", "referrals": [dict(r) for r in rows], "total_commission": round(total, 2)})

@leads_bp.route("/all-referrals", methods=["GET"])
@login_required
def all_referrals():
    if session.get("username") != "admin":
        return jsonify({"status": "error", "message": "Admin only"}), 403
    db   = get_db()
    rows = db.execute("SELECT * FROM lead_referrals ORDER BY created_at DESC").fetchall()
    db.close()
    return jsonify({"status": "ok", "referrals": [dict(r) for r in rows]})

@leads_bp.route("/approve-referral", methods=["POST"])
@login_required
def approve_referral():
    if session.get("username") != "admin":
        return jsonify({"status": "error", "message": "Admin only"}), 403
    data       = request.get_json(force=True) or {}
    ref_id     = data.get("id")
    commission = float(data.get("commission", 10.0))
    action     = data.get("action", "approve")
    db = get_db()
    if action == "approve":
        db.execute("UPDATE lead_referrals SET status='approved', commission_amount=?, approved_at=CURRENT_TIMESTAMP WHERE id=?", (commission, ref_id))
    else:
        db.execute("UPDATE lead_referrals SET status='rejected' WHERE id=?", (ref_id,))
    db.commit(); db.close()
    return jsonify({"status": "ok"})

@leads_bp.route("/referrals-page", methods=["GET"])
@login_required
def referrals_page():
    return render_template("referrals.html")
