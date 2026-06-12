from flask import Blueprint, render_template, session
from services.auth_service import login_required

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html", username=session.get("username", ""))
