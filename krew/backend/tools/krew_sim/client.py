"""HTTP client for the Krew chat API."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import BASE_URL, API_PREFIX, TIMEOUT_SECONDS


@dataclass
class TurnResult:
    """Result of a single conversation turn."""
    turn_number: int
    employee_id: str
    message_sent: str
    status_code: int
    response_body: dict
    agent: str = ""
    response_text: str = ""
    conversation_id: str = ""
    latency_ms: float = 0.0
    error: str | None = None


class KrewClient:
    """Synchronous HTTP client for krew-sim."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(timeout=TIMEOUT_SECONDS)

    def send_message(self, employee_id: str, message: str, turn_number: int = 1) -> TurnResult:
        """Send a chat message and return the structured result."""
        url = f"{self.base_url}{API_PREFIX}"
        payload = {"employee_id": employee_id, "message": message}

        start = time.monotonic()
        try:
            r = self.http.post(url, json=payload)
            latency_ms = (time.monotonic() - start) * 1000
        except httpx.RequestError as exc:
            return TurnResult(
                turn_number=turn_number,
                employee_id=employee_id,
                message_sent=message,
                status_code=0,
                response_body={},
                error=f"Connection error: {exc}",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        body = {}
        try:
            body = r.json()
        except Exception:
            pass

        result = TurnResult(
            turn_number=turn_number,
            employee_id=employee_id,
            message_sent=message,
            status_code=r.status_code,
            response_body=body,
            agent=body.get("agent", ""),
            response_text=body.get("response", ""),
            conversation_id=body.get("conversation_id", ""),
            latency_ms=latency_ms,
        )
        if r.status_code >= 400:
            result.error = f"HTTP {r.status_code}: {body.get('detail', r.text[:200])}"
        return result

    def reset_conversation(self, employee_id: str) -> bool:
        """Reset the active web conversation for an employee."""
        url = f"{self.base_url}{API_PREFIX}/reset/{employee_id}"
        try:
            r = self.http.post(url)
            return r.status_code == 200
        except httpx.RequestError:
            return False

    def list_employees(self) -> list[dict]:
        """Fetch all employees from the chat API."""
        url = f"{self.base_url}{API_PREFIX}/employees"
        try:
            r = self.http.get(url)
            return r.json() if r.status_code == 200 else []
        except httpx.RequestError:
            return []

    def close(self):
        self.http.close()
