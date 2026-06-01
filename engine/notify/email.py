# engine/notify/email.py
"""Builds the daily digest (pure) and sends it via SMTP (side effect)."""
import os
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple


def build_digest(suggestions: List[Dict], scanned_at: str) -> Optional[Tuple[str, str]]:
    """Return (subject, body) for the digest, or None if there are no suggestions."""
    if not suggestions:
        return None
    ranked = sorted(suggestions, key=lambda s: s["conviction"], reverse=True)
    subject = "Investment Scout: {} opportunity(ies) found".format(len(ranked))
    lines = ["Scan completed {}".format(scanned_at), ""]
    for s in ranked:
        lines.append("{}  [{}]  conviction {}/100  ${:.2f}".format(
            s["symbol"], s["tier"].upper(), s["conviction"], s.get("price", 0.0)))
        if s.get("summary"):
            lines.append("    {}".format(s["summary"]))
        for r in s.get("reasons", []):
            lines.append("    - {}".format(r))
        lines.append("")
    lines.append("These are research leads, not advice. Do your own diligence.")
    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    """Send via SMTP using env-var credentials. Returns True on success.

    Required env vars (set as GitHub secrets):
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
    If any are missing, logs and returns False (does not raise).
    """
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("EMAIL_TO")
    if not all([host, port, user, password, to_addr]):
        print("email skipped: SMTP env vars not fully set")
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, int(port)) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        return True
    except Exception as exc:
        print("email send failed: {}".format(exc))
        return False
