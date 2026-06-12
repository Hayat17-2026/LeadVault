from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, request, jsonify
from services.scraper_service import scrape_url
from services.activity_service import log_activity

fetch_bp = Blueprint("fetch", __name__)

@fetch_bp.route("/", methods=["GET"])
@login_required
@rate_limited
def fetch_page():
    return render_template("fetch.html")

@fetch_bp.route("/scrape", methods=["POST"])
@login_required
@rate_limited
def scrape():
    try:
        data = request.get_json(force=True)
        url  = (data.get("url") or "").strip()
        if not url:
            return jsonify({"status": "error", "message": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = scrape_url(url)
        log_activity("fetch", f"Fetched {url}")
        return jsonify({"status": "ok", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
