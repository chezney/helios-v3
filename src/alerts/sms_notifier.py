"""
SMS notification channel using Twilio.

Sends critical alerts via SMS for immediate attention.
"""

import os
from typing import List
import logging

from .alert_manager import Alert, AlertLevel

logger = logging.getLogger(__name__)


class SMSNotifier:
    """
    SMS notification channel using Twilio.

    Configuration via environment variables:
    - TWILIO_ACCOUNT_SID: Twilio account SID
    - TWILIO_AUTH_TOKEN: Twilio auth token
    - TWILIO_FROM_NUMBER: Twilio phone number (format: +1234567890)
    - ALERT_SMS_TO: Comma-separated list of recipient phone numbers
    - ALERT_SMS_LEVEL: Minimum alert level for SMS (default: CRITICAL)

    Note: Only sends SMS for CRITICAL alerts by default to avoid SMS spam.
    """

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER", "")
        self.to_numbers = os.getenv("ALERT_SMS_TO", "").split(",")
        self.to_numbers = [n.strip() for n in self.to_numbers if n.strip()]

        # Minimum alert level for SMS (to avoid spam)
        level_str = os.getenv("ALERT_SMS_LEVEL", "CRITICAL").upper()
        self.min_level = {
            "INFO": AlertLevel.INFO,
            "WARNING": AlertLevel.WARNING,
            "CRITICAL": AlertLevel.CRITICAL
        }.get(level_str, AlertLevel.CRITICAL)

        # Validate configuration
        if not self.account_sid or not self.auth_token or not self.from_number:
            logger.warning("SMS notifier not configured (missing Twilio credentials)")
            self.enabled = False
            self.client = None
        elif not self.to_numbers:
            logger.warning("SMS notifier not configured (missing ALERT_SMS_TO)")
            self.enabled = False
            self.client = None
        else:
            try:
                # Import Twilio client
                from twilio.rest import Client
                self.client = Client(self.account_sid, self.auth_token)
                self.enabled = True
                logger.info(f"SMS notifier configured: {self.from_number} -> {len(self.to_numbers)} recipients (min level: {self.min_level.value})")
            except ImportError:
                logger.warning("SMS notifier disabled: twilio package not installed (pip install twilio)")
                self.enabled = False
                self.client = None

    async def send(self, alert: Alert):
        """Send alert via SMS."""
        if not self.enabled:
            logger.debug("SMS notifier disabled, skipping")
            return

        # Check if alert level is high enough
        level_priority = {
            AlertLevel.INFO: 1,
            AlertLevel.WARNING: 2,
            AlertLevel.CRITICAL: 3
        }
        if level_priority[alert.level] < level_priority[self.min_level]:
            logger.debug(f"SMS skipped: {alert.level.value} < {self.min_level.value}")
            return

        try:
            # Create SMS message (max 160 chars recommended)
            message = self._create_message(alert)

            # Send to all recipients
            for to_number in self.to_numbers:
                try:
                    msg = self.client.messages.create(
                        body=message,
                        from_=self.from_number,
                        to=to_number
                    )
                    logger.info(f"SMS alert sent: {alert.title} to {to_number} (SID: {msg.sid})")
                except Exception as e:
                    logger.error(f"Failed to send SMS to {to_number}: {e}")

            logger.info(f"SMS alert sent: {alert.title} to {len(self.to_numbers)} recipients")

        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}")
            raise

    def _create_message(self, alert: Alert) -> str:
        """
        Create SMS message body.

        Keep it short (SMS limit is 160 chars for single message).
        """
        # Emoji for visual alert level
        emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨"
        }

        # Create concise message
        message = f"{emoji.get(alert.level, '🔔')} HELIOS ALERT\n"
        message += f"[{alert.level.value.upper()}] {alert.title}\n"
        message += f"{alert.message[:100]}"  # Truncate long messages

        # Add critical details if available
        if alert.metadata:
            if "value" in alert.metadata:
                message += f"\nValue: {alert.metadata['value']}"
            if "threshold" in alert.metadata:
                message += f"\nThreshold: {alert.metadata['threshold']}"

        # Ensure within reasonable SMS length (160-320 chars for 1-2 messages)
        if len(message) > 320:
            message = message[:317] + "..."

        return message


# Test function
async def test_sms_notifier():
    """Test SMS configuration."""
    notifier = SMSNotifier()

    if not notifier.enabled:
        print("❌ SMS notifier not configured")
        print("\nSet these environment variables:")
        print("  TWILIO_ACCOUNT_SID=your-account-sid")
        print("  TWILIO_AUTH_TOKEN=your-auth-token")
        print("  TWILIO_FROM_NUMBER=+1234567890")
        print("  ALERT_SMS_TO=+1234567890")
        print("\nInstall Twilio SDK:")
        print("  pip install twilio")
        return False

    # Create test alert
    from datetime import datetime
    test_alert = Alert(
        level=AlertLevel.CRITICAL,  # Use CRITICAL to ensure it sends
        title="SMS Notifier Test",
        message="This is a test SMS from Helios V3.0 alert system. SMS notifications are working!",
        source="system",
        timestamp=datetime.utcnow(),
        metadata={"test": True}
    )

    try:
        await notifier.send(test_alert)
        print("✅ Test SMS sent successfully!")
        print(f"Sent to: {', '.join(notifier.to_numbers)}")
        return True
    except Exception as e:
        print(f"❌ Failed to send test SMS: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_sms_notifier())
