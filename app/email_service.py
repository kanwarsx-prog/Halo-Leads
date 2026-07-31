import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os

from app.config import get_settings


import socket

class IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is not None and timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)
        
        # Resolve IPv4 explicitly
        addr = socket.gethostbyname(host)
        sock.connect((addr, port))
        return sock

def send_email(to_email: str, subject: str, body: str, attachment_path: str | None = None) -> None:
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

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
        msg.attach(part)

    with IPv4SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.set_debuglevel(1)
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
