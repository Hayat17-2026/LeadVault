"""
LeadVault AI — powered by Claude (Anthropic).
Falls back to the rule-based engine if ANTHROPIC_API_KEY is not set.
"""
import os
import anthropic
from database.db import get_db

# ── Per-user conversation history (in-memory, max 20 messages / 10 turns) ──
_history: dict[str, list] = {}
MAX_HISTORY = 20


def _get_db_context() -> str:
    """Pull live stats from the database to inject into the system prompt."""
    try:
        db = get_db()
        total    = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        new      = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        high     = db.execute("SELECT COUNT(*) FROM leads WHERE score >= 75").fetchone()[0]
        mid      = db.execute("SELECT COUNT(*) FROM leads WHERE score >= 50 AND score < 75").fetchone()[0]
        low      = db.execute("SELECT COUNT(*) FROM leads WHERE score < 50").fetchone()[0]
        emailed  = db.execute("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL AND email != ''").fetchone()[0]
        top      = db.execute("SELECT name, score, email FROM leads ORDER BY score DESC LIMIT 1").fetchone()
        recent   = db.execute("SELECT name, status FROM leads ORDER BY rowid DESC LIMIT 3").fetchall()
        db.close()

        top_str    = f"{top['name']} (score {top['score']})" if top else "none yet"
        recent_str = ", ".join(f"{r['name']} [{r['status']}]" for r in recent) if recent else "none"

        return f"""
LIVE DATABASE SNAPSHOT:
- Total leads: {total}
- New leads: {new}
- High priority (score 75+): {high}
- Medium priority (50-74): {mid}
- Low priority (<50): {low}
- Leads with email: {emailed}
- Top lead by score: {top_str}
- 3 most recent leads: {recent_str}
"""
    except Exception:
        return "\nLIVE DATABASE SNAPSHOT: (unavailable)\n"


_SYSTEM_PROMPT = """You are LeadVault AI, the intelligent built-in assistant for the LeadVault lead management system.
LeadVault is a Final Year Project (FYP) at the Islamic University of Lebanon, CCE department.

THE SYSTEM — 5-step lead pipeline:
1. Search     — discover leads using Google/SerpAPI
2. Web Fetch  — scrape websites for contact details (name, email, phone, description)
3. AI Classify — score each lead 0-100 and assign High/Medium/Low priority
4. Leads DB   — manage, filter, export, find duplicates
5. Email Outreach — send individual or bulk emails with templates

SCORING LOGIC (0-100):
• Keyword match    → up to +40
• B2B/wholesale    → +20
• Email available  → +15
• Phone available  → +10
• Active business  → +10
Tiers: High ≥ 75 · Medium 50-74 · Low < 50

PAGES & FEATURES:
- Dashboard: KPI cards, charts (platform, score distribution, daily activity, status)
- Activity Log: full audit trail of every action
- Users: admin-only user management (add/delete staff)
- Settings: app info and system status

ANSWER STYLE:
- Be concise but complete. Use HTML <strong> tags for emphasis. Use <br> for line breaks when listing steps.
- Be friendly and professional. You can use 1-2 relevant emojis per message.
- If the user asks in Arabic, answer in Arabic (Lebanese dialect is fine).
- If asked something outside LeadVault, briefly answer then redirect to how you can help with leads.
- Never invent data — only state numbers you can see in the live snapshot below.
"""


def get_ai_response(message: str, username: str = "guest") -> str:
    """
    Return a Claude-powered response.
    Falls back to rule-based if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _rule_based(message)

    # Build per-user history
    if username not in _history:
        _history[username] = []

    _history[username].append({"role": "user", "content": message})

    # Trim to max history
    if len(_history[username]) > MAX_HISTORY:
        _history[username] = _history[username][-MAX_HISTORY:]

    # Inject live DB context into system prompt
    system = _SYSTEM_PROMPT + _get_db_context()

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system,
            messages=_history[username],
        )
        reply = response.content[0].text

        _history[username].append({"role": "assistant", "content": reply})
        return reply

    except anthropic.AuthenticationError:
        _history[username].pop()
        return "⚠️ <strong>API key error</strong> — please check your ANTHROPIC_API_KEY in the environment."
    except anthropic.RateLimitError:
        _history[username].pop()
        return "⚠️ Rate limit reached. Please wait a moment and try again."
    except Exception as e:
        _history[username].pop()
        return f"⚠️ AI service error: {e}"


def clear_history(username: str) -> None:
    """Clear conversation history for a user."""
    _history.pop(username, None)


# ── Rule-based fallback (used when no API key is configured) ─────────────────
def _rule_based(message: str) -> str:
    msg = message.lower().strip()

    if any(w in msg for w in ["how many leads", "total leads", "count", "كم عميل"]):
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        new   = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        db.close()
        return f"You have <strong>{total} leads</strong> in your database — <strong>{new}</strong> are new and awaiting contact. 📊"

    if any(w in msg for w in ["best lead", "top lead", "highest score", "أفضل"]):
        db = get_db()
        row = db.execute("SELECT name, score, email FROM leads ORDER BY score DESC LIMIT 1").fetchone()
        db.close()
        if row:
            return f"Your top lead is <strong>{row['name']}</strong> (score <strong>{row['score']}/100</strong>). {('Contact: ' + row['email']) if row['email'] else ''} 🎯"
        return "No leads yet — try running a Search first! 🔍"

    if any(w in msg for w in ["with email", "have email", "contactable"]):
        db = get_db()
        cnt = db.execute("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL AND email != ''").fetchone()[0]
        db.close()
        return f"<strong>{cnt} leads</strong> have an email address. Use the Email Outreach module to contact them. 📧"

    if any(w in msg for w in ["how to search", "find leads", "كيف"]):
        return "To find leads:<br>1. Go to <strong>Search &amp; Research</strong><br>2. Enter keywords (e.g. 'phone dealer Beirut')<br>3. Pick platform &amp; region<br>4. Click <strong>Run Search</strong><br>5. Queue the leads you want → Fetch → Classify 🔍"

    if any(w in msg for w in ["score", "scoring", "quality"]):
        return "Leads are scored 0–100:<br>• Keyword match → up to +40<br>• B2B signals → +20<br>• Email → +15<br>• Phone → +10<br>• Active business → +10<br><br>🟢 75+ = High &nbsp; 🟡 50-74 = Medium &nbsp; 🔴 &lt;50 = Low"

    if any(w in msg for w in ["email", "outreach", "contact", "send"]):
        return "Use the <strong>Email Outreach</strong> module to send individual or bulk emails. Each lead card also has a <strong>WhatsApp</strong> shortcut. 📨"

    if any(w in msg for w in ["duplicate", "clean", "remove dup"]):
        return "Go to <strong>Leads Database</strong> → click <strong>Find Duplicates</strong>. The system flags same-email/phone leads and removes the lower-scored one. 🧹"

    if any(w in msg for w in ["export", "pdf", "csv", "download", "report"]):
        return "In <strong>Leads Database</strong> use the toolbar to export as <strong>PDF report</strong> or <strong>CSV file</strong>. 📄"

    if any(w in msg for w in ["marketing", "advice", "tip", "strategy"]):
        return "💡 Tips:<br>• Target High-priority leads (75+) first<br>• Personalize your emails<br>• Follow up within 48 hours<br>• Update lead status after each contact<br>• WhatsApp works better than email in MENA!"

    if any(w in msg for w in ["hello", "hi", "hey", "مرحبا", "السلام"]):
        return "Hello! 👋 I'm LeadVault AI. Ask me about your leads, pipeline steps, scoring, or marketing tips!"

    if any(w in msg for w in ["help", "what can you do"]):
        return "I can help with:<br>• 📊 Lead statistics<br>• 🎯 Finding your best leads<br>• 🔍 How to search &amp; fetch<br>• 📧 Email outreach guidance<br>• 💡 Marketing strategy<br>• 🧹 Cleaning duplicates"

    if any(w in msg for w in ["thank", "thanks", "شكرا"]):
        return "You're welcome! 😊 Feel free to ask anything else."

    return "I'm your LeadVault assistant! Try asking:<br>• \"How many leads do I have?\"<br>• \"Who is my best lead?\"<br>• \"How does scoring work?\"<br>• \"Give me marketing tips\""
