"""
Email notification channel using SMTP.

Sends formatted email alerts for trading system events.
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List
import logging

from .alert_manager import Alert, AlertLevel

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Email notification channel.

    Configuration via environment variables:
    - SMTP_HOST: SMTP server hostname (default: smtp.gmail.com)
    - SMTP_PORT: SMTP server port (default: 587)
    - SMTP_USER: SMTP username/email
    - SMTP_PASSWORD: SMTP password or app-specific password
    - ALERT_EMAIL_FROM: From email address
    - ALERT_EMAIL_TO: Comma-separated list of recipient emails
    """

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("ALERT_EMAIL_FROM", self.username)
        self.to_emails = os.getenv("ALERT_EMAIL_TO", "").split(",")
        self.to_emails = [e.strip() for e in self.to_emails if e.strip()]

        # Validate configuration
        if not self.username or not self.password:
            logger.warning("Email notifier not configured (missing SMTP_USER or SMTP_PASSWORD)")
            self.enabled = False
        elif not self.to_emails:
            logger.warning("Email notifier not configured (missing ALERT_EMAIL_TO)")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Email notifier configured: {self.from_email} -> {', '.join(self.to_emails)}")

    async def send(self, alert: Alert):
        """Send alert via email."""
        if not self.enabled:
            logger.debug("Email notifier disabled, skipping")
            return

        try:
            # Create email message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.level.value.upper()}] Helios Alert: {alert.title}"
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)

            # Create email body (HTML and plain text)
            text_body = self._create_text_body(alert)
            html_body = self._create_html_body(alert)

            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")

            msg.attach(part1)
            msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email alert sent: {alert.title} to {len(self.to_emails)} recipients")

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            raise

    def _create_text_body(self, alert: Alert) -> str:
        """Create plain text email body."""
        return f"""
HELIOS V3.0 TRADING SYSTEM ALERT
{'-' * 50}

Level:     {alert.level.value.upper()}
Title:     {alert.title}
Source:    {alert.source}
Timestamp: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}

Message:
{alert.message}

{'-' * 50}
This is an automated alert from Helios V3.0 Trading System.
        """.strip()

    def _create_html_body(self, alert: Alert) -> str:
        """Create HTML email body with styling."""
        # Color based on alert level
        colors = {
            AlertLevel.INFO: "#3498db",       # Blue
            AlertLevel.WARNING: "#f39c12",    # Orange
            AlertLevel.CRITICAL: "#e74c3c"    # Red
        }
        color = colors.get(alert.level, "#95a5a6")

        metadata_html = ""
        if alert.metadata:
            metadata_html = "<h3>Details:</h3><ul>"
            for key, value in alert.metadata.items():
                metadata_html += f"<li><strong>{key}:</strong> {value}</li>"
            metadata_html += "</ul>"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            background-color: white;
            border-radius: 8px;
            padding: 30px;
            max-width: 600px;
            margin: 0 auto;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            background-color: {color};
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            margin: -30px -30px 20px -30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .level-badge {{
            display: inline-block;
            background-color: rgba(255,255,255,0.3);
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 14px;
            margin-top: 10px;
        }}
        .info-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .info-table td {{
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .info-table td:first-child {{
            font-weight: bold;
            color: #555;
            width: 30%;
        }}
        .message {{
            background-color: #f9f9f9;
            padding: 15px;
            border-left: 4px solid {color};
            margin: 20px 0;
            line-height: 1.6;
        }}
        .footer {{
            text-align: center;
            color: #888;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚠️ Helios Trading System Alert</h1>
            <span class="level-badge">{alert.level.value.upper()}</span>
        </div>

        <h2>{alert.title}</h2>

        <table class="info-table">
            <tr>
                <td>Source</td>
                <td>{alert.source}</td>
            </tr>
            <tr>
                <td>Timestamp</td>
                <td>{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
            </tr>
            <tr>
                <td>Severity</td>
                <td style="color: {color}; font-weight: bold;">{alert.level.value.upper()}</td>
            </tr>
        </table>

        <h3>Message:</h3>
        <div class="message">
            {alert.message}
        </div>

        {metadata_html}

        <div class="footer">
            This is an automated alert from <strong>Helios V3.0 Trading System</strong><br>
            Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
        """.strip()


# Test function
async def test_email_notifier():
    """Test email configuration."""
    notifier = EmailNotifier()

    if not notifier.enabled:
        print("❌ Email notifier not configured")
        print("\nSet these environment variables:")
        print("  SMTP_USER=your-email@gmail.com")
        print("  SMTP_PASSWORD=your-app-password")
        print("  ALERT_EMAIL_TO=recipient@example.com")
        return False

    # Create test alert
    test_alert = Alert(
        level=AlertLevel.INFO,
        title="Email Notifier Test",
        message="This is a test email from Helios V3.0 alert system. If you received this, email notifications are working correctly!",
        source="system",
        timestamp=datetime.utcnow(),
        metadata={"test": True, "version": "3.0.0"}
    )

    try:
        await notifier.send(test_alert)
        print("✅ Test email sent successfully!")
        print(f"Sent to: {', '.join(notifier.to_emails)}")
        return True
    except Exception as e:
        print(f"❌ Failed to send test email: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_email_notifier())
