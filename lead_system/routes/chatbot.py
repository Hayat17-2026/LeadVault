from flask import Blueprint, request, jsonify, session
from services.auth_service import login_required, rate_limited
from services.chatbot_service import get_ai_response, clear_history

chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.route("/ask", methods=["POST"])
@login_required
@rate_limited
def ask():
    d       = request.get_json(force=True)
    message = (d.get("message") or "").strip()
    if not message:
        return jsonify({"status": "error", "reply": "Please type a message."})
    username = session.get("username", "guest")
    reply    = get_ai_response(message, username)
    return jsonify({"status": "ok", "reply": reply})


@chatbot_bp.route("/clear", methods=["POST"])
@login_required
def clear():
    clear_history(session.get("username", "guest"))
    return jsonify({"status": "ok"})
