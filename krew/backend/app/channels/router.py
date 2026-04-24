"""Channel router — normalizes inbound messages and routes outbound replies."""
import logging

from app.channels.whatsapp import WhatsAppAdapter
from app.channels.slack import SlackAdapter

logger = logging.getLogger(__name__)

# Supported channels
SUPPORTED_CHANNELS = {"whatsapp", "slack", "teams", "email"}


class ChannelRouter:
    """Routes messages between Krew agents and communication channels.

    Normalizes inbound payloads from different channels into a consistent
    format and dispatches outbound messages to the correct adapter.
    """

    def __init__(self):
        self.whatsapp = WhatsAppAdapter()
        self.slack = SlackAdapter()

    def parse_inbound(self, channel: str, payload: dict) -> dict:
        """Parse an inbound webhook payload into a normalized message dict.

        Args:
            channel: The channel identifier (whatsapp, slack, teams, email).
            payload: The raw webhook payload from the channel.

        Returns:
            Normalized dict with keys:
                - sender_id: Unique identifier for the sender on that channel
                - message: The text content of the message
                - channel: The channel name
                - metadata: Channel-specific metadata dict

        Raises:
            ValueError: If the channel is unsupported or the payload cannot be parsed.
        """
        if channel not in SUPPORTED_CHANNELS:
            raise ValueError(
                f"Unsupported channel: {channel}. "
                f"Supported channels: {', '.join(sorted(SUPPORTED_CHANNELS))}"
            )

        parsed: dict | None = None

        if channel == "whatsapp":
            parsed = self.whatsapp.parse_webhook(payload)

        elif channel == "slack":
            parsed = self.slack.parse_event(payload)

        elif channel == "teams":
            parsed = self._parse_teams_payload(payload)

        elif channel == "email":
            parsed = self._parse_email_payload(payload)

        if parsed is None:
            raise ValueError(
                f"Could not parse inbound payload for channel '{channel}'"
            )

        # Ensure consistent shape
        return {
            "sender_id": parsed.get("sender_id", ""),
            "message": parsed.get("message", ""),
            "channel": channel,
            "metadata": parsed.get("metadata", {}),
        }

    async def send_outbound(
        self, channel: str, recipient_id: str, message: str
    ) -> None:
        """Route an outbound message to the correct channel adapter.

        Args:
            channel: The channel to send through (whatsapp, slack, teams, email).
            recipient_id: Channel-specific recipient identifier:
                - whatsapp: phone number (e.g., "966501234567")
                - slack: channel ID (e.g., "C01ABCDEF")
                - teams: user ID or conversation ID
                - email: email address
            message: The text message to send.

        Raises:
            ValueError: If the channel is unsupported.
            httpx.HTTPStatusError: If the underlying API call fails.
        """
        if channel not in SUPPORTED_CHANNELS:
            raise ValueError(f"Unsupported channel: {channel}")

        logger.info(
            "Sending outbound message via %s to %s (%d chars)",
            channel,
            recipient_id,
            len(message),
        )

        if channel == "whatsapp":
            await self.whatsapp.send_message(
                phone_number=recipient_id, text=message
            )

        elif channel == "slack":
            await self.slack.send_message(channel_id=recipient_id, text=message)

        elif channel == "teams":
            await self._send_teams_message(recipient_id, message)

        elif channel == "email":
            await self._send_email_message(recipient_id, message)

    # ---- Microsoft Teams (placeholder with structure) ----

    @staticmethod
    def _parse_teams_payload(payload: dict) -> dict | None:
        """Parse Microsoft Teams Bot Framework webhook payload.

        Teams Bot Framework activity structure:
        {
            "type": "message",
            "from": {"id": "...", "name": "..."},
            "text": "hello",
            "conversation": {"id": "..."},
            "serviceUrl": "https://smba.trafficmanager.net/..."
        }
        """
        try:
            if payload.get("type") != "message":
                return None

            from_user = payload.get("from", {})
            sender_id = from_user.get("id", "")
            message_text = payload.get("text", "")

            if not sender_id or not message_text:
                return None

            return {
                "sender_id": sender_id,
                "message": message_text,
                "metadata": {
                    "conversation_id": payload.get("conversation", {}).get("id"),
                    "service_url": payload.get("serviceUrl"),
                    "sender_name": from_user.get("name"),
                    "activity_id": payload.get("id"),
                },
            }

        except (KeyError, TypeError) as exc:
            logger.error("Failed to parse Teams payload: %s", exc)
            return None

    @staticmethod
    async def _send_teams_message(recipient_id: str, message: str) -> None:
        """Send a message via Microsoft Teams Bot Framework.

        Uses the Bot Framework REST API to send a proactive message
        or reply to a conversation.
        """
        # Teams requires the serviceUrl from the original activity,
        # plus a stored conversation reference. For now, log a warning.
        # Full implementation requires storing conversation references
        # and using the Bot Framework connector client.
        logger.warning(
            "Teams outbound not yet fully implemented. "
            "recipient=%s, message_len=%d",
            recipient_id,
            len(message),
        )
        raise NotImplementedError(
            "Teams outbound messaging requires Bot Framework connector setup. "
            "See: https://learn.microsoft.com/en-us/azure/bot-service/"
        )

    # ---- Email (placeholder with structure) ----

    @staticmethod
    def _parse_email_payload(payload: dict) -> dict | None:
        """Parse an inbound email webhook payload.

        Expected structure (e.g., from SendGrid Inbound Parse or similar):
        {
            "from": "user@example.com",
            "subject": "Leave request",
            "text": "I want to request annual leave...",
            "to": "hr@krew.sa"
        }
        """
        try:
            sender_id = payload.get("from", "")
            message_text = payload.get("text", "") or payload.get("body", "")

            if not sender_id or not message_text:
                return None

            return {
                "sender_id": sender_id,
                "message": message_text,
                "metadata": {
                    "subject": payload.get("subject"),
                    "to": payload.get("to"),
                    "cc": payload.get("cc"),
                },
            }

        except (KeyError, TypeError) as exc:
            logger.error("Failed to parse email payload: %s", exc)
            return None

    @staticmethod
    async def _send_email_message(recipient_id: str, message: str) -> None:
        """Send an email reply.

        Full implementation would use an email service like SendGrid, SES, or SMTP.
        """
        logger.warning(
            "Email outbound not yet fully implemented. "
            "recipient=%s, message_len=%d",
            recipient_id,
            len(message),
        )
        raise NotImplementedError(
            "Email outbound messaging requires email service configuration. "
            "Configure SendGrid or AWS SES credentials."
        )
