"""Slack Bot API adapter — for companies using Slack as their primary workspace."""
import logging
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter:
    """Handles inbound event parsing and outbound messaging for Slack Bot API."""

    @staticmethod
    def parse_event(payload: dict) -> dict | None:
        """Parse a Slack Events API payload into a normalized message.

        Handles two cases:
        1. URL verification challenge (returns the challenge for handshake).
        2. Message events from users (ignoring bot messages and subtypes).

        Slack event structure for messages:
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U01ABCDEF",
                "text": "hello",
                "channel": "C01ABCDEF",
                "ts": "1234567890.123456"
            },
            "team_id": "T01ABCDEF"
        }

        Returns:
            Normalized dict with {sender_id, message} or None if not a user message.
        """
        try:
            # Handle Slack URL verification challenge
            if payload.get("type") == "url_verification":
                logger.info("Slack URL verification challenge received")
                return {
                    "sender_id": "__challenge__",
                    "message": "",
                    "metadata": {
                        "challenge": payload.get("challenge", ""),
                        "is_challenge": True,
                    },
                }

            if payload.get("type") != "event_callback":
                return None

            event = payload.get("event", {})

            # Only handle direct messages (type=message, no subtype means user-sent)
            if event.get("type") != "message":
                return None

            # Ignore bot messages, message_changed, and other subtypes
            if event.get("subtype") is not None:
                return None

            # Ignore messages from bots
            if event.get("bot_id"):
                return None

            sender_id = event.get("user", "")
            message_text = event.get("text", "")

            if not sender_id or not message_text:
                return None

            return {
                "sender_id": sender_id,
                "message": message_text,
                "metadata": {
                    "channel_id": event.get("channel"),
                    "thread_ts": event.get("thread_ts"),
                    "ts": event.get("ts"),
                    "team_id": payload.get("team_id"),
                },
            }

        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Failed to parse Slack event: %s", exc)
            return None

    @staticmethod
    async def send_message(
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict:
        """Send a message via Slack Web API (chat.postMessage).

        Args:
            channel_id: The Slack channel or DM channel ID.
            text: The message text to send.
            thread_ts: Optional thread timestamp to reply in a thread.

        Returns:
            The Slack API response as a dict.

        Raises:
            httpx.HTTPStatusError: If the HTTP request fails.
            ValueError: If Slack API returns ok=false.
        """
        payload: dict = {
            "channel": channel_id,
            "text": text,
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {settings.slack_bot_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("ok"):
                error = result.get("error", "unknown_error")
                logger.error("Slack API error: %s", error)
                raise ValueError(f"Slack API error: {error}")

            logger.info("Slack message sent to channel %s", channel_id)
            return result
