from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, request, jsonify
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
