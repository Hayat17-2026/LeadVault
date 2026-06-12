import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL CONFIGURATION — loaded from config.py (edit keys there, not here)
# ══════════════════════════════════════════════════════════════════════════════
import os as _os
SENDER_EMAIL    = "your_email@gmail.com"
SENDER_PASSWORD = "your_16_char_app_password"
try:
    _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _config_path = _os.path.join(_ROOT, "config.py")
    _cfg = {}
    with open(_config_path, "r", encoding="utf-8") as _f:
        exec(_f.read(), _cfg)
    SENDER_EMAIL    = _cfg.get("SENDER_EMAIL", SENDER_EMAIL)
    SENDER_PASSWORD = _cfg.get("SENDER_PASSWORD", SENDER_PASSWORD)
except Exception as e:
    print(f"[config] email_service could not load config.py: {e}")
SENDER_NAME     = "LeadVault"
# ══════════════════════════════════════════════════════════════════════════════

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 587


def _send(to_email: str, subject: str, html_body: str) -> dict:
    """Internal — sends an HTML email via Gmail SMTP."""
    if SENDER_EMAIL == "your_email@gmail.com" or not SENDER_PASSWORD or SENDER_PASSWORD == "YOUR_GMAIL_APP_PASSWORD":
        return {"status": "error", "message": "Email not configured. Add your Gmail in email_service.py"}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()

        print(f"[email] Sent to {to_email}: {subject}")
        return {"status": "ok", "message": f"Email sent to {to_email}"}

    except smtplib.SMTPAuthenticationError:
        return {"status": "error", "message": "Gmail login failed. Check email & app password."}
    except Exception as e:
        print(f"[email] Error: {e}")
        return {"status": "error", "message": str(e)}


def send_welcome_to_lead(lead_email: str, lead_name: str) -> dict:
    """Send a professional welcome/outreach email to a lead."""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:#0d1b2a;padding:24px;text-align:center;">
        <h1 style="color:#00c2ff;margin:0;font-size:22px;">LeadVault</h1>
        <p style="color:rgba(255,255,255,0.6);margin:4px 0 0;font-size:13px;">AI-Powered Business Outreach</p>
      </div>
      <div style="padding:32px 28px;">
        <h2 style="color:#1a202c;font-size:20px;">Hello {lead_name},</h2>
        <p style="color:#4a5568;font-size:15px;line-height:1.7;">
          We came across your business and believe there could be a great opportunity
          for collaboration. We specialize in connecting businesses with the right partners
          and customers.
        </p>
        <p style="color:#4a5568;font-size:15px;line-height:1.7;">
          We would love to discuss how we can help grow your business. Please feel free
          to reply to this email at your convenience.
        </p>
        <div style="text-align:center;margin:28px 0;">
          <a href="mailto:{SENDER_EMAIL}" style="background:#00c2ff;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Get in Touch</a>
        </div>
        <p style="color:#a0aec0;font-size:13px;">Best regards,<br/>The LeadAI Team</p>
      </div>
      <div style="background:#f7fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;">
        <p style="color:#a0aec0;font-size:11px;margin:0;">This message was sent by LeadVault — CCE FYP Project 2025</p>
      </div>
    </div>
    """
    return _send(lead_email, f"Partnership Opportunity — {lead_name}", html)


def send_lead_added_confirmation(admin_email: str, lead_name: str, lead_score: int) -> dict:
    """Notify admin when a new lead is added to the database."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:#0d1b2a;padding:20px;text-align:center;">
        <h1 style="color:#00c2ff;margin:0;font-size:20px;">New Lead Added</h1>
      </div>
      <div style="padding:28px;">
        <p style="color:#4a5568;font-size:15px;">A new lead has been added to your database:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:10px;background:#f7fafc;font-weight:600;color:#1a202c;">Lead Name</td><td style="padding:10px;border-bottom:1px solid #eee;">{lead_name}</td></tr>
          <tr><td style="padding:10px;background:#f7fafc;font-weight:600;color:#1a202c;">AI Score</td><td style="padding:10px;border-bottom:1px solid #eee;">{lead_score}/100</td></tr>
          <tr><td style="padding:10px;background:#f7fafc;font-weight:600;color:#1a202c;">Added At</td><td style="padding:10px;border-bottom:1px solid #eee;">{now}</td></tr>
        </table>
      </div>
    </div>
    """
    return _send(admin_email, f"New Lead: {lead_name} (Score {lead_score})", html)


def send_report_to_admin(admin_email: str, total: int, new: int, avg_score: float) -> dict:
    """Send a summary report of the leads database to the admin."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:#0d1b2a;padding:24px;text-align:center;">
        <h1 style="color:#00c2ff;margin:0;font-size:22px;">LeadAI — Database Report</h1>
        <p style="color:rgba(255,255,255,0.6);margin:4px 0 0;font-size:13px;">{now}</p>
      </div>
      <div style="padding:28px;">
        <div style="display:flex;gap:12px;text-align:center;margin-bottom:20px;">
          <div style="flex:1;background:#f7fafc;border-radius:8px;padding:16px;">
            <div style="font-size:28px;font-weight:700;color:#00c2ff;">{total}</div>
            <div style="font-size:12px;color:#718096;">Total Leads</div>
          </div>
          <div style="flex:1;background:#f7fafc;border-radius:8px;padding:16px;">
            <div style="font-size:28px;font-weight:700;color:#00c88a;">{new}</div>
            <div style="font-size:12px;color:#718096;">New Leads</div>
          </div>
          <div style="flex:1;background:#f7fafc;border-radius:8px;padding:16px;">
            <div style="font-size:28px;font-weight:700;color:#1a202c;">{avg_score}</div>
            <div style="font-size:12px;color:#718096;">Avg Score</div>
          </div>
        </div>
        <p style="color:#4a5568;font-size:14px;">Your lead collection system is performing well. Keep up the outreach!</p>
      </div>
    </div>
    """
    return _send(admin_email, f"LeadAI Database Report — {total} leads", html)