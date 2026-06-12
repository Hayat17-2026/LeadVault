import hashlib
import os
import time
import random
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

# ══════════════════════════════════════════════════════════════════════════════
#  USER ACCOUNTS
#  Each user: password (hashed), email, security question + answer (hashed)
# ══════════════════════════════════════════════════════════════════════════════
USERS = {
    "admin": {
        "password":      hashlib.sha256("Admin@123".encode()).hexdigest(),
        "email":         "hayatseifeddine8@gmail.com",
        "role":          "admin",
        "security_q":    "What is your favorite color?",
        "security_a":    hashlib.sha256("blue".encode()).hexdigest(),
    },
    "hala": {
        "password":      hashlib.sha256("Hala@2025".encode()).hexdigest(),
        "email":         "hayatseifeddine8@gmail.com",
        "role":          "staff",
        "security_q":    "What city were you born in?",
        "security_a":    hashlib.sha256("beirut".encode()).hexdigest(),
    },
}

# ── Rate limiting store ───────────────────────────────────────────────────────
_rate_store = {}
RATE_LIMIT  = 200
RATE_WINDOW = 60

# ── OTP store: { username: { "code": "123456", "expires": timestamp } } ───────
_otp_store = {}
OTP_VALIDITY = 300   # 5 minutes


def hash_value(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()

def validate_password_strength(password: str) -> dict:
    """Check password meets requirements: 8+ chars, a number, a symbol."""
    import re
    if len(password) < 8:
        return {"valid": False, "message": "Password must be at least 8 characters"}
    if not re.search(r"\d", password):
        return {"valid": False, "message": "Password must contain a number"}
    if not re.search(r"[#@!$%^&*?_\-]", password):
        return {"valid": False, "message": "Password must contain a symbol (#@!$%^&*?)"}
    return {"valid": True, "message": "Strong password"}

def get_user_role(username: str) -> str:
    user = USERS.get(username)
    return user.get("role", "staff") if user else "staff"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def resolve_username(login_id: str) -> str:
    """Accept either a username OR an email and return the matching username."""
    login_id = (login_id or "").strip().lower()
    if login_id in USERS:
        return login_id
    # try matching by email
    for uname, data in USERS.items():
        if data.get("email", "").lower() == login_id:
            return uname
    return login_id  # not found — return as-is so login fails normally

def check_credentials(username: str, password: str) -> bool:
    user = USERS.get(username)
    if not user:
        return False
    return user["password"] == hash_password(password)

def get_user_email(username: str):
    user = USERS.get(username)
    return user["email"] if user else None

def get_security_question(username: str):
    user = USERS.get(username)
    return user["security_q"] if user else None

def check_security_answer(username: str, answer: str) -> bool:
    user = USERS.get(username)
    if not user:
        return False
    return user["security_a"] == hash_value(answer)

def user_exists(username: str) -> bool:
    return username in USERS


# ── OTP functions ─────────────────────────────────────────────────────────────
def generate_otp(username: str) -> str:
    code = str(random.randint(100000, 999999))
    _otp_store[username] = {"code": code, "expires": time.time() + OTP_VALIDITY}
    return code

def verify_otp(username: str, code: str) -> bool:
    rec = _otp_store.get(username)
    if not rec:
        return False
    if time.time() > rec["expires"]:
        del _otp_store[username]
        return False
    return rec["code"] == code.strip()

def reset_password(username: str, new_password: str) -> bool:
    if username not in USERS:
        return False
    USERS[username]["password"] = hash_password(new_password)
    _otp_store.pop(username, None)
    return True


# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json:
                return jsonify({"status": "error", "message": "Unauthorized"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated

def rate_limited(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip  = request.remote_addr
        now = time.time()
        rec = _rate_store.get(ip, {"count": 0, "window_start": now})
        if now - rec["window_start"] > RATE_WINDOW:
            rec = {"count": 0, "window_start": now}
        rec["count"] += 1
        _rate_store[ip] = rec
        if rec["count"] > RATE_LIMIT:
            if request.is_json:
                return jsonify({"status": "error", "message": "Rate limit exceeded. Wait 60 seconds."}), 429
            return "<h2 style='font-family:Arial;color:red;text-align:center;margin-top:15%;'>Too many requests — please wait 60 seconds.</h2>", 429
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    return session.get("username", "unknown")


# ══════════════════════════════════════════════════════════════════════════════
#  USER MANAGEMENT (admin only)
# ══════════════════════════════════════════════════════════════════════════════
def add_user(username: str, password: str, email: str, role: str = "staff") -> dict:
    """Add a new user. Only callable by admin."""
    username = username.strip().lower()
    if not username or not password:
        return {"status": "error", "message": "Username and password required"}
    if username in USERS:
        return {"status": "error", "message": "Username already exists"}
    if len(password) < 5:
        return {"status": "error", "message": "Password must be at least 5 characters"}

    USERS[username] = {
        "password":   hash_password(password),
        "email":      email or "",
        "role":       role,
        "security_q": "What is your favorite color?",
        "security_a": hash_value("blue"),
    }
    return {"status": "ok", "message": f"User '{username}' created"}

def delete_user(username: str) -> dict:
    """Delete a user. Cannot delete admin."""
    username = username.strip().lower()
    if username == "admin":
        return {"status": "error", "message": "Cannot delete the admin account"}
    if username not in USERS:
        return {"status": "error", "message": "User not found"}
    del USERS[username]
    return {"status": "ok", "message": f"User '{username}' deleted"}

def list_users() -> list:
    """Return all users (without passwords)."""
    return [
        {"username": u, "email": USERS[u].get("email", ""), "role": USERS[u].get("role", "staff")}
        for u in USERS
    ]

def is_admin() -> bool:
    """Check if current session user is admin."""
    return session.get("username") == "admin"


# ══════════════════════════════════════════════════════════════════════════════
#  CAPTCHA (simple math / image-style challenge)
# ══════════════════════════════════════════════════════════════════════════════
_captcha_store = {}   # { session_id: answer }

def generate_captcha() -> dict:
    """Generate a simple math CAPTCHA. Returns question + stores answer."""
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    op = random.choice(["+", "-", "×"])
    if op == "+":
        answer = a + b
    elif op == "-":
        a, b = max(a, b), min(a, b)  # avoid negatives
        answer = a - b
    else:
        answer = a * b
    question = f"{a} {op} {b}"
    # store answer keyed by a random token
    token = str(random.randint(100000, 999999))
    _captcha_store[token] = str(answer)
    return {"question": question, "token": token}

def verify_captcha(token: str, answer: str) -> bool:
    """Check CAPTCHA answer."""
    correct = _captcha_store.get(token)
    if correct is None:
        return False
    is_ok = str(answer).strip() == correct
    _captcha_store.pop(token, None)  # one-time use
    return is_ok


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE CAPTCHA — "select all images of X" (uses emoji-based icon grid)
# ══════════════════════════════════════════════════════════════════════════════
_img_captcha_store = {}   # { token: set_of_correct_indices }

# Categories with their emoji and some distractors
_CAPTCHA_CATEGORIES = {
    "car":        "🚗", "motorcycle": "🏍️", "bird": "🐦", "cat": "🐱",
    "dog":        "🐶", "tree": "🌳", "flower": "🌸", "fish": "🐟",
    "airplane":   "✈️", "boat": "⛵", "bicycle": "🚲", "bus": "🚌",
}

def generate_image_captcha() -> dict:
    """Generate an image-grid CAPTCHA. Returns target + 9 emoji tiles + token."""
    target = random.choice(list(_CAPTCHA_CATEGORIES.keys()))
    target_emoji = _CAPTCHA_CATEGORIES[target]

    # How many correct tiles (2-4)
    num_correct = random.randint(2, 4)
    grid = [None] * 9
    correct_indices = random.sample(range(9), num_correct)
    for i in correct_indices:
        grid[i] = target_emoji

    # Fill rest with random distractors (different category)
    distractors = [e for k, e in _CAPTCHA_CATEGORIES.items() if k != target]
    for i in range(9):
        if grid[i] is None:
            grid[i] = random.choice(distractors)

    token = str(random.randint(100000, 999999))
    _img_captcha_store[token] = set(correct_indices)

    return {
        "target": target,
        "target_label": f"Select all images with a {target}",
        "grid": grid,
        "token": token
    }

def verify_image_captcha(token: str, selected: list) -> bool:
    """Check if selected tiles match the correct ones exactly."""
    correct = _img_captcha_store.get(token)
    if correct is None:
        return False
    try:
        sel = set(int(x) for x in selected)
    except Exception:
        sel = set()
    _img_captcha_store.pop(token, None)  # one-time use
    return sel == correct


# ══════════════════════════════════════════════════════════════════════════════
#  LETTER CAPTCHA — random uppercase letters the user must type
# ══════════════════════════════════════════════════════════════════════════════
import string
_letter_captcha_store = {}   # { token: answer }

def generate_letter_captcha() -> dict:
    """Generate a 5-character letter CAPTCHA."""
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    token = str(random.randint(100000, 999999))
    _letter_captcha_store[token] = letters
    return {"letters": letters, "token": token}

def verify_letter_captcha(token: str, answer: str) -> bool:
    """Verify typed letters (case-insensitive, one-time use)."""
    correct = _letter_captcha_store.get(token)
    if correct is None:
        return False
    is_ok = (answer or "").strip().upper() == correct
    _letter_captcha_store.pop(token, None)
    return is_ok