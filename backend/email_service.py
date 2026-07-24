"""Resend transactional email service."""
import os
import asyncio
import logging
import resend

logger = logging.getLogger(__name__)


def _configure():
    key = os.environ.get("RESEND_API_KEY", "")
    resend.api_key = key
    return key


def _sender():
    return os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


def _app_url():
    return os.environ.get("APP_PUBLIC_URL", "").rstrip("/")


async def send_email(to: str, subject: str, html: str) -> dict:
    key = _configure()
    if not key or key.startswith("re_placeholder"):
        logger.warning(f"[MOCK EMAIL - no RESEND_API_KEY] to={to} subject={subject}")
        return {"mocked": True, "to": to, "subject": subject}
    try:
        result = await asyncio.to_thread(
            resend.Emails.send,
            {"from": _sender(), "to": [to], "subject": subject, "html": html},
        )
        return {"mocked": False, "id": result.get("id")}
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        raise


def _wrap(inner_html: str, preheader: str = "") -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>PAPERBRAIN</title></head>
<body style="margin:0;padding:0;background:#050505;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#fafafa;">
<span style="display:none;visibility:hidden;opacity:0;height:0;width:0;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;padding:40px 0;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#0a0a0a;border:1px solid #1a1a1a;">
      <tr><td style="padding:32px;border-bottom:1px solid #1a1a1a;">
        <div style="display:inline-block;background:#3366FF;padding:6px 10px;color:#fff;font-weight:800;letter-spacing:-0.02em;">PAPERBRAIN</div>
      </td></tr>
      <tr><td style="padding:32px;color:#fafafa;line-height:1.55;font-size:15px;">
        {inner_html}
      </td></tr>
      <tr><td style="padding:20px 32px;border-top:1px solid #1a1a1a;color:#71717a;font-size:11px;font-family:'IBM Plex Mono',ui-monospace,monospace;">
        This email was sent from PAPERBRAIN — your private AI knowledge assistant.<br/>
        If you didn&rsquo;t request this, you can safely ignore it.
      </td></tr>
    </table>
  </td></tr>
</table></body></html>"""


def verification_email(name: str, link: str) -> tuple[str, str]:
    subject = "Verify your PAPERBRAIN email"
    body = f"""
<h1 style="font-size:24px;font-weight:800;letter-spacing:-0.02em;margin:0 0 12px 0;">Welcome, {name}.</h1>
<p style="color:#a1a1aa;margin:0 0 24px 0;">Confirm your email to activate your private knowledge archive.</p>
<a href="{link}" style="display:inline-block;background:#3366FF;color:#fff;padding:12px 20px;text-decoration:none;font-weight:600;">Verify email</a>
<p style="color:#71717a;font-size:12px;margin:24px 0 0 0;">Or paste this link into your browser:<br/><span style="color:#a1a1aa;word-break:break-all;">{link}</span></p>
<p style="color:#71717a;font-size:12px;margin:16px 0 0 0;">This link expires in 24 hours.</p>
"""
    return subject, _wrap(body, "Verify your email to activate your archive.")


def password_reset_email(name: str, link: str) -> tuple[str, str]:
    subject = "Reset your PAPERBRAIN password"
    body = f"""
<h1 style="font-size:24px;font-weight:800;letter-spacing:-0.02em;margin:0 0 12px 0;">Reset your password</h1>
<p style="color:#a1a1aa;margin:0 0 24px 0;">Hi {name}, click the button below to choose a new password. This link expires in 1 hour.</p>
<a href="{link}" style="display:inline-block;background:#3366FF;color:#fff;padding:12px 20px;text-decoration:none;font-weight:600;">Reset password</a>
<p style="color:#71717a;font-size:12px;margin:24px 0 0 0;">Or paste this link into your browser:<br/><span style="color:#a1a1aa;word-break:break-all;">{link}</span></p>
<p style="color:#71717a;font-size:12px;margin:16px 0 0 0;">If you didn&rsquo;t request a password reset, ignore this email.</p>
"""
    return subject, _wrap(body, "Reset your PAPERBRAIN password.")
