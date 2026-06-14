import os
from flask import Flask, request
from routes.search    import search_bp
from routes.fetch     import fetch_bp
from routes.leads     import leads_bp
from routes.dashboard import dashboard_bp
from routes.classify  import classify_bp
from routes.auth      import auth_bp
from routes.email     import email_bp
from routes.activity  import activity_bp
from routes.chatbot   import chatbot_bp
from routes.settings  import settings_bp
from database.db      import init_db
from services.auth_service import seed_db_users, load_db_users

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "leadvault-fyp-2026-secret-key")

# Security headers on every response
@app.after_request
def add_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"]        = "DENY"
    resp.headers["X-XSS-Protection"]       = "1; mode=block"
    resp.headers["Referrer-Policy"]        = "no-referrer"
    return resp

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(search_bp,   url_prefix="/search")
app.register_blueprint(fetch_bp,    url_prefix="/fetch")
app.register_blueprint(leads_bp,    url_prefix="/leads")
app.register_blueprint(classify_bp, url_prefix="/classify")
app.register_blueprint(email_bp,    url_prefix="/email")
app.register_blueprint(activity_bp, url_prefix="/activity")
app.register_blueprint(chatbot_bp,  url_prefix="/chatbot")
app.register_blueprint(settings_bp)

init_db()
seed_db_users()
load_db_users()

if __name__ == "__main__":
    print("✅  Database initialized")
    print("🔐  Security: login required, rate limiting active")
    print("🚀  Starting LeadAI System...")
    print("👉  Open http://127.0.0.1:5000 in your browser")
    app.run(debug=True)
