from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from services.auth_service import (
    check_credentials, user_exists, get_security_question, check_security_answer,
    get_user_email, generate_otp, verify_otp, reset_password,
    generate_captcha, verify_captcha, add_user, delete_user, list_users, is_admin,
    generate_image_captcha,
    generate_letter_captcha, verify_letter_captcha,
    resolve_username, get_user_role,
    register_user, list_pending_registrations, approve_registration
)

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")

@auth_bp.route("/login", methods=["POST"])
def login():
    data     = request.get_json(force=True)
    login_id = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    captcha_token  = data.get("captcha_token", "")
    captcha_answer = data.get("captcha_answer", "")

    if not login_id or not password:
        return jsonify({"status": "error", "message": "Please enter your username/email and password"}), 400

    # Verify LETTER CAPTCHA
    if not verify_letter_captcha(captcha_token, captcha_answer):
        return jsonify({"status": "error", "message": "Security check failed — please type the letters correctly and try again."}), 400

    username = resolve_username(login_id)

    if not user_exists(username):
        return jsonify({"status": "error", "message": "No account found with that username or email."}), 401

    if check_credentials(username, password):
        selected_role = data.get("role", "")
        actual_role = get_user_role(username)
        if selected_role and selected_role != actual_role:
            nice = "Administrator" if actual_role == "admin" else "Staff Member"
            return jsonify({"status": "error", "message": f"This account is registered as {nice}. Please select the correct account type."}), 403

        session["logged_in"] = True
        session["username"]  = username
        session["role"]      = actual_role
        try:
            from services.activity_service import log_activity
            log_activity("login", f"User {username} logged in")
        except Exception:
            pass
        return jsonify({"status": "ok", "redirect": "/"})
    return jsonify({"status": "error", "message": "Incorrect password. Please try again."}), 401


@auth_bp.route("/login/check", methods=["POST"])
def login_check():
    """Pre-validate credentials before showing CAPTCHA."""
    data     = request.get_json(force=True)
    login_id = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not login_id or not password:
        return jsonify({"status": "error", "message": "Please enter your username/email and password."}), 400

    username = resolve_username(login_id)

    if not user_exists(username):
        return jsonify({"status": "error", "message": "No account found with that username or email."}), 401

    if not check_credentials(username, password):
        return jsonify({"status": "error", "message": "Incorrect password. Please try again."}), 401

    selected_role = data.get("role", "")
    actual_role   = get_user_role(username)
    if selected_role and selected_role != actual_role:
        nice = "Administrator" if actual_role == "admin" else "Staff Member"
        return jsonify({"status": "error", "message": f"This account is registered as {nice}. Please select the correct account type."}), 403

    return jsonify({"status": "ok"})

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))

# ── FORGOT PASSWORD FLOW ──────────────────────────────────────────────────────

@auth_bp.route("/forgot", methods=["GET"])
def forgot_page():
    return render_template("forgot.html")

# Step 1: Check username exists, return their security question
@auth_bp.route("/forgot/check-user", methods=["POST"])
def check_user():
    data     = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    if not user_exists(username):
        return jsonify({"status": "error", "message": "Username not found"}), 404
    return jsonify({"status": "ok", "question": get_security_question(username)})

# Step 2: Verify security answer, then send OTP to email
@auth_bp.route("/forgot/verify-security", methods=["POST"])
def verify_security():
    data     = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    answer   = (data.get("answer") or "").strip()

    if not check_security_answer(username, answer):
        return jsonify({"status": "error", "message": "Wrong answer to security question"}), 401

    # Generate and email OTP
    from services.email_service import _send
    code  = generate_otp(username)
    email = get_user_email(username)
    masked = email[:3] + "***" + email[email.index("@"):]

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:#0d1b2a;padding:24px;text-align:center;">
        <h1 style="color:#00c2ff;margin:0;font-size:20px;">Password Reset Code</h1>
      </div>
      <div style="padding:32px;text-align:center;">
        <p style="color:#4a5568;font-size:15px;">Your one-time verification code is:</p>
        <div style="font-size:36px;font-weight:700;letter-spacing:8px;color:#0d1b2a;background:#f0f9ff;padding:16px;border-radius:8px;margin:16px 0;">{code}</div>
        <p style="color:#a0aec0;font-size:13px;">This code expires in 5 minutes. If you didn't request this, ignore this email.</p>
      </div>
    </div>
    """
    result = _send(email, "Your LeadAI Password Reset Code", html)
    if result["status"] != "ok":
        return jsonify({"status": "error", "message": "Could not send code: " + result["message"]}), 500

    return jsonify({"status": "ok", "message": f"Code sent to {masked}"})

# Step 3: Verify OTP code
@auth_bp.route("/forgot/verify-otp", methods=["POST"])
def verify_code():
    data     = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    code     = (data.get("code") or "").strip()
    if verify_otp(username, code):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Invalid or expired code"}), 401

# Step 4: Set new password
@auth_bp.route("/forgot/reset", methods=["POST"])
def do_reset():
    data        = request.get_json(force=True)
    username    = (data.get("username") or "").strip().lower()
    code        = (data.get("code") or "").strip()
    new_password= (data.get("password") or "").strip()

    if not verify_otp(username, code):
        return jsonify({"status": "error", "message": "Session expired. Start over."}), 401
    if len(new_password) < 5:
        return jsonify({"status": "error", "message": "Password must be at least 5 characters"}), 400

    reset_password(username, new_password)
    return jsonify({"status": "ok", "message": "Password reset! You can now login."})


# ── CAPTCHA ───────────────────────────────────────────────────────────────────
@auth_bp.route("/captcha", methods=["GET"])
def get_captcha():
    return jsonify(generate_captcha())

@auth_bp.route("/image-captcha", methods=["GET"])
def get_image_captcha():
    return jsonify(generate_image_captcha())

@auth_bp.route("/letter-captcha", methods=["GET"])
def get_letter_captcha():
    return jsonify(generate_letter_captcha())


# ── USER MANAGEMENT (admin only) ──────────────────────────────────────────────
@auth_bp.route("/users/list", methods=["GET"])
def get_users():
    if not session.get("logged_in"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if not is_admin():
        return jsonify({"status": "error", "message": "Admin only"}), 403
    return jsonify({"status": "ok", "users": list_users()})

@auth_bp.route("/users/add", methods=["POST"])
def create_user():
    if not session.get("logged_in") or not is_admin():
        return jsonify({"status": "error", "message": "Admin only"}), 403
    d = request.get_json(force=True)
    username = (d.get("username") or "").strip()
    password = (d.get("password") or "").strip()
    confirm  = (d.get("confirm") or "").strip()
    email    = (d.get("email") or "").strip()
    captcha_token  = d.get("captcha_token", "")
    captcha_answer = d.get("captcha_answer", "")

    # Password confirmation check
    if password != confirm:
        return jsonify({"status": "error", "message": "Passwords do not match"}), 400
    # CAPTCHA check
    if not verify_captcha(captcha_token, captcha_answer):
        return jsonify({"status": "error", "message": "CAPTCHA verification failed"}), 400

    # Password strength check
    from services.auth_service import validate_password_strength
    strength = validate_password_strength(password)
    if not strength["valid"]:
        return jsonify({"status": "error", "message": strength["message"]}), 400

    result = add_user(username, password, email)
    code = 200 if result["status"] == "ok" else 400
    return jsonify(result), code

@auth_bp.route("/users/delete", methods=["POST"])
def remove_user():
    if not session.get("logged_in") or not is_admin():
        return jsonify({"status": "error", "message": "Admin only"}), 403
    d = request.get_json(force=True)
    result = delete_user(d.get("username", ""))
    return jsonify(result)

@auth_bp.route("/users", methods=["GET"])
def users_page():
    if not session.get("logged_in"):
        return redirect(url_for("auth.login_page"))
    if not is_admin():
        return redirect(url_for("dashboard.index"))
    return render_template("users.html")


# ── REGISTRATION (public self-signup) ────────────────────────────────────────
@auth_bp.route("/register", methods=["GET"])
def register_page():
    if session.get("logged_in"):
        return redirect(url_for("dashboard.index"))
    return render_template("register.html")

@auth_bp.route("/register", methods=["POST"])
def do_register():
    d = request.get_json(force=True)
    username   = (d.get("username") or "").strip().lower()
    password   = (d.get("password") or "").strip()
    confirm    = (d.get("confirm") or "").strip()
    email      = (d.get("email") or "").strip()
    full_name  = (d.get("full_name") or "").strip()
    security_q = (d.get("security_q") or "").strip()
    security_a = (d.get("security_a") or "").strip()

    if password != confirm:
        return jsonify({"status": "error", "message": "Passwords do not match"}), 400
    if not email or "@" not in email:
        return jsonify({"status": "error", "message": "Valid email is required"}), 400
    if not security_a:
        return jsonify({"status": "error", "message": "Security answer is required"}), 400

    result = register_user(username, password, email, full_name, security_q, security_a)
    code = 200 if result["status"] == "ok" else 400
    return jsonify(result), code


# ── PENDING REGISTRATIONS (admin only) ───────────────────────────────────────
@auth_bp.route("/users/pending", methods=["GET"])
def get_pending():
    if not session.get("logged_in") or not is_admin():
        return jsonify({"status": "error", "message": "Admin only"}), 403
    return jsonify({"status": "ok", "pending": list_pending_registrations()})

@auth_bp.route("/users/approve-reg", methods=["POST"])
def approve_reg():
    if not session.get("logged_in") or not is_admin():
        return jsonify({"status": "error", "message": "Admin only"}), 403
    d      = request.get_json(force=True)
    uid    = d.get("id")
    action = d.get("action", "approve")
    result = approve_registration(uid, action)
    return jsonify(result)