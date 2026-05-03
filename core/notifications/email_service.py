import logging
import resend
from config.app_settings import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.get("resend_api_key", "")

FROM_EMAIL = settings.get("from_email", "")
TO_EMAIL = settings.get("to_email", "")


def send_email(subject: str, html: str) -> None:
    if not resend.api_key or not FROM_EMAIL or not TO_EMAIL:
        logger.warning("Email not configured — skipping alert")
        return

    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": TO_EMAIL,
            "subject": subject,
            "html": html,
        })
        logger.info("Alert email sent | subject=%s", subject)
    except Exception as e:
        logger.error("Failed to send alert email | %s", e)
