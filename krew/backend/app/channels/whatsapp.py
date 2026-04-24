"""WhatsApp Cloud API adapter — primary channel for Krew in Saudi Arabia."""
import logging
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAdapter:
    """Handles inbound webhook parsing and outbound messaging for WhatsApp Cloud API."""

    @staticmethod
    def parse_webhook(payload: dict) -> dict | None:
        """Parse a WhatsApp Cloud API webhook payload into a normalized message.

        WhatsApp webhook structure:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "...",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "..."},
                        "contacts": [{"profile": {"name": "..."}, "wa_id": "966..."}],
                        "messages": [{
                            "from": "966...",
                            "id": "wamid...",
                            "timestamp": "...",
                            "text": {"body": "..."},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        Returns:
            Normalized dict with {sender_id, message} or None if not a text message.
        """
        try:
            entry = payload.get("entry", [])
            if not entry:
                return None

            changes = entry[0].get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]

            # Only handle text messages for now; media support can be added later
            if msg.get("type") != "text":
                logger.info(
                    "Ignoring non-text WhatsApp message type: %s", msg.get("type")
                )
                return None

            sender_id = msg.get("from", "")
            message_text = msg.get("text", {}).get("body", "")

            if not sender_id or not message_text:
                return None

            # Extract optional contact name
            contacts = value.get("contacts", [])
            sender_name = None
            if contacts:
                sender_name = contacts[0].get("profile", {}).get("name")

            return {
                "sender_id": sender_id,
                "message": message_text,
                "metadata": {
                    "message_id": msg.get("id"),
                    "timestamp": msg.get("timestamp"),
                    "sender_name": sender_name,
                    "phone_number_id": value.get("metadata", {}).get(
                        "phone_number_id"
                    ),
                },
            }

        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Failed to parse WhatsApp webhook: %s", exc)
            return None

    @staticmethod
    async def send_message(phone_number: str, text: str) -> dict:
        """Send a text message via WhatsApp Cloud API.

        Args:
            phone_number: Recipient phone number in international format (e.g., 966501234567).
            text: The message text to send.

        Returns:
            The API response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns an error status.
        """
        url = (
            f"{WHATSAPP_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.whatsapp_access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone_number,
                    "type": "text",
                    "text": {"preview_url": False, "body": text},
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info("WhatsApp message sent to %s", phone_number)
            return result
