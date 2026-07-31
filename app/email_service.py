import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings


def send_email(to_email: str, subject: str, body: str) -> None:
    """
    Sends an email using the SMTP settings from the configuration.
    Raises an exception if the configuration is missing or SMTP fails.
    """
    settings = get_settings()

    if not all([settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password, settings.sender_email]):
        raise ValueError("SMTP configuration is incomplete. Please check your .env settings.")

    msg = MIMEMultipart()
    msg['From'] = f"{settings.sender_name} <{settings.sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
