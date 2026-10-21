"""Minimal SMTP sender.

Uses the Python stdlib (no extra dependency) on a worker thread so it doesn't
block the event loop. If SMTP isn't configured, it runs in dev mode: the
message is logged instead of sent, and callers surface the OTP another way
(an X-Dev-OTP response header) so the flow stays testable without a mailbox.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str, html: str | None = None) -> bool:
    """Send an email. Returns True if actually dispatched via SMTP, False in
    dev mode (logged only).

    When `html` is given the message goes out multipart/alternative: clients
    that can't or won't render HTML fall back to `body`, and multipart mail
    tends to be treated more kindly by spam filters than HTML alone.
    """
    if not settings.smtp_configured:
        logger.warning(
            "SMTP not configured — email to %s NOT sent.\nSubject: %s\n%s", to, subject, body
        )
        return False

    def _send() -> None:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_starttls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

    await asyncio.to_thread(_send)
    logger.info("sent email to %s (%s)", to, subject)
    return True
