from services.auth_service import login_required, rate_limited
from flask import Blueprint, render_template, jsonify
from services.activity_service import get_recent_activity

activity_bp = Blueprint("activity", __name__)

@activity_bp.route("/", methods=["GET"])
@login_required
@rate_limited
def activity_page():
    return render_template("activity.html")

@activity_bp.route("/all", methods=["GET"])
@login_required
@rate_limited
def all_activity():
    return jsonify(get_recent_activity(100))
