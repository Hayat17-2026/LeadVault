from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, request, jsonify
from services.ai_service import classify_lead, classify_batch
from database.db import get_db

classify_bp = Blueprint("classify", __name__)

@classify_bp.route("/", methods=["GET"])
@login_required
@rate_limited
def classify_page():
    return render_template("classify.html")

@classify_bp.route("/run", methods=["POST"])
@login_required
@rate_limited
def run_classify():
    """Classify a single lead with AI."""
    d = request.get_json()
    result = classify_lead(
        name     = d.get("name", ""),
        snippet  = d.get("snippet", ""),
        interests= d.get("interests", ""),
        keywords = d.get("keywords", [])
    )
    return jsonify({"status": "ok", "result": result})

@classify_bp.route("/all", methods=["POST"])
@login_required
@rate_limited
def classify_all_leads():
    """Classify all leads in the database and update their scores."""
    d        = request.get_json()
    keywords = d.get("keywords", ["electronics", "phone", "laptop"])
    db       = get_db()
    leads    = [dict(r) for r in db.execute("SELECT * FROM leads").fetchall()]

    updated = 0
    for lead in leads:
        ai = classify_lead(
            name     = lead.get("name", ""),
            snippet  = lead.get("interests", ""),
            interests= lead.get("interests", ""),
            keywords = keywords
        )
        # Update score and interests in DB
        db.execute(
            "UPDATE leads SET score=?, interests=? WHERE id=?",
            (ai["quality_score"], ", ".join(ai["interests"]), lead["id"])
        )
        updated += 1

    db.commit()
    db.close()
    return jsonify({"status": "ok", "updated": updated})
