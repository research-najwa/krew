"""Tests for the WebSocket chat.send round-trip.

We mock the DB session and the orchestrator so the test never touches
PostgreSQL — the goal is to verify the envelope wire contract, not the
agent logic.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure test-safe env BEFORE importing app modules (same pattern as test_auth.py)
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRY_HOURS", "24")
os.environ.setdefault("APP_ENV", "development")

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.jwt import create_chat_token  # noqa: E402
from app.models.conversation import ConversationStatus  # noqa: E402
from app.models.employee import EmployeeStatus  # noqa: E402


TENANT_ID = uuid.uuid4()
EMPLOYEE_ID = uuid.uuid4()


class _FakeResult:
    """Minimal stand-in for SQLAlchemy Result/ScalarResult."""
    def __init__(self, value=None, iterable=None):
        self._value = value
        self._iterable = iterable or []

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def scalars(self):
        parent = self

        class _S:
            def all(self_inner):
                return list(parent._iterable)

        return _S()


class _FakeSession:
    """Async-session stand-in that feeds scripted responses to execute()."""

    def __init__(self, employee, conversation):
        self._employee = employee
        self._conversation = conversation
        self._execute_count = 0
        self.added: list = []
        self.committed = False

    async def execute(self, stmt):  # noqa: ARG002 — we don't parse the statement
        self._execute_count += 1
        # Order of queries in _handle_chat_send:
        #   1. SELECT employee
        #   2. SELECT most-recent active conversation
        #   3. SELECT history messages
        if self._execute_count == 1:
            return _FakeResult(value=self._employee)
        if self._execute_count == 2:
            return _FakeResult(value=self._conversation)
        if self._execute_count == 3:
            return _FakeResult(iterable=[])
        return _FakeResult(value=None, iterable=[])

    def add(self, obj):
        # Emulate the DB populating server defaults on flush/commit.
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    async def refresh(self, obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


def _build_fake_employee():
    emp = MagicMock()
    emp.id = EMPLOYEE_ID
    emp.tenant_id = TENANT_ID
    emp.status = EmployeeStatus.active
    emp.first_name = "Sara"
    emp.full_name = "Sara Al-Qahtani"
    emp.preferred_language = "en"
    emp.department_id = None
    return emp


def _build_fake_conversation():
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.tenant_id = TENANT_ID
    conv.employee_id = EMPLOYEE_ID
    conv.agent_name = "deema"
    conv.status = ConversationStatus.active
    conv.topic = None
    conv.language = "en"
    conv.last_mentioned_agent = None
    return conv


@pytest.fixture
def patched_app(monkeypatch):
    """Patch the ws module's DB session + orchestrator + rbac helpers."""
    import app.api.ws as ws_mod
    from app.main import app

    fake_employee = _build_fake_employee()
    fake_conv = _build_fake_conversation()
    fake_session = _FakeSession(fake_employee, fake_conv)

    @asynccontextmanager
    async def _fake_async_session():
        yield fake_session

    monkeypatch.setattr(ws_mod, "async_session", _fake_async_session)

    # Patch the lazily-imported orchestrator
    import app.agents.orchestrator as orch_mod

    fake_orch = MagicMock()
    fake_orch.handle_message = AsyncMock(
        return_value=("deema", "Hello Sara, how can I help?", None)
    )
    monkeypatch.setattr(
        orch_mod, "AgentOrchestrator", MagicMock(return_value=fake_orch)
    )

    # Patch the role derivation helper so it doesn't touch the DB
    import app.utils.employee_role as role_mod

    async def _fake_derive_role(db, tenant_id, employee_id):  # noqa: ARG001
        return "employee"

    monkeypatch.setattr(role_mod, "derive_employee_role", _fake_derive_role)

    # Disable Redis pubsub + rate limiter during the test
    async def _no_redis():
        return None

    monkeypatch.setattr(ws_mod, "get_redis", _no_redis)

    return {
        "app": app,
        "session": fake_session,
        "orchestrator": fake_orch,
        "conversation": fake_conv,
        "employee": fake_employee,
    }


def _make_token() -> str:
    return create_chat_token(EMPLOYEE_ID, TENANT_ID, "Sara Al-Qahtani")


def test_ws_chat_send_round_trip(patched_app):
    token = _make_token()
    client = TestClient(patched_app["app"])

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        # 1. connection.ready
        ready = ws.receive_json()
        assert ready["type"] == "connection.ready"
        assert ready["payload"]["user"]["id"] == str(EMPLOYEE_ID)
        assert ready["payload"]["user"]["tenant_id"] == str(TENANT_ID)

        # 2. Send chat.send
        send_id = "test-envelope-1"
        ws.send_json({
            "v": 1,
            "id": send_id,
            "type": "chat.send",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "agent": "deema",
                "text": "Hi Deema",
                "conversation_id": None,
                "locale": "en",
            },
        })

        events = []
        # Collect 3 envelopes: user msg, assistant msg, complete
        for _ in range(3):
            events.append(ws.receive_json())

    types = [e["type"] for e in events]
    assert types == [
        "chat.message.created",
        "chat.message.created",
        "chat.complete",
    ]

    user_evt, assistant_evt, complete_evt = events

    # All should ref the original envelope id
    for evt in events:
        assert evt["ref"] == send_id

    assert user_evt["payload"]["role"] == "user"
    assert user_evt["payload"]["text"] == "Hi Deema"
    assert user_evt["payload"]["conversation_id"]

    assert assistant_evt["payload"]["role"] == "assistant"
    assert assistant_evt["payload"]["agent"] == "deema"
    assert assistant_evt["payload"]["text"] == "Hello Sara, how can I help?"

    assert complete_evt["payload"]["agent"] == "deema"
    assert complete_evt["payload"]["conversation_id"] == user_evt["payload"]["conversation_id"]

    # Orchestrator was invoked exactly once with the scrubbed text
    patched_app["orchestrator"].handle_message.assert_awaited_once()
    call_kwargs = patched_app["orchestrator"].handle_message.await_args.kwargs
    assert call_kwargs["message"] == "Hi Deema"
    assert call_kwargs["employee_id"] == str(EMPLOYEE_ID)


def test_ws_chat_send_routes_requested_agent(patched_app):
    """chat.send with agent=mohammad must reach the orchestrator as current_agent=mohammad."""
    # Orchestrator replies as mohammad
    patched_app["orchestrator"].handle_message = AsyncMock(
        return_value=("mohammad", "Recruitment desk here — how can I help?", None)
    )

    token = _make_token()
    client = TestClient(patched_app["app"])

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # connection.ready
        ws.send_json({
            "v": 1,
            "id": "route-1",
            "type": "chat.send",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "agent": "mohammad",
                "text": "I want to hire a backend engineer",
                "conversation_id": None,
                "locale": "en",
            },
        })
        events = [ws.receive_json() for _ in range(3)]

    assert [e["type"] for e in events] == [
        "chat.message.created",
        "chat.message.created",
        "chat.complete",
    ]
    assistant_evt = events[1]
    assert assistant_evt["payload"]["agent"] == "mohammad"

    patched_app["orchestrator"].handle_message.assert_awaited_once()
    call_kwargs = patched_app["orchestrator"].handle_message.await_args.kwargs
    assert call_kwargs["current_agent"] == "mohammad"
    assert call_kwargs["message"] == "I want to hire a backend engineer"


def test_ws_chat_send_empty_text_emits_error(patched_app):
    token = _make_token()
    client = TestClient(patched_app["app"])

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # connection.ready
        ws.send_json({
            "v": 1,
            "id": "empty-1",
            "type": "chat.send",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {"agent": "deema", "text": "   ", "locale": "en"},
        })
        evt = ws.receive_json()

    assert evt["type"] == "error"
    assert evt["ref"] == "empty-1"
    assert evt["payload"]["code"] == "invalid_payload"
    # Orchestrator must NOT have been called
    patched_app["orchestrator"].handle_message.assert_not_awaited()


def test_ws_chat_send_orchestrator_failure_emits_error(patched_app):
    token = _make_token()

    async def _boom(**kwargs):  # noqa: ARG001
        raise RuntimeError("agent exploded")

    patched_app["orchestrator"].handle_message = AsyncMock(side_effect=_boom)

    client = TestClient(patched_app["app"])
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # connection.ready
        ws.send_json({
            "v": 1,
            "id": "boom-1",
            "type": "chat.send",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {"agent": "deema", "text": "hi", "locale": "en"},
        })
        evt = ws.receive_json()
        # Connection stays open — send another message type (pong) to prove it.
        ws.send_json({
            "v": 1,
            "id": "pong-1",
            "type": "pong",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {},
        })

    assert evt["type"] == "error"
    assert evt["ref"] == "boom-1"
    assert evt["payload"]["code"] == "agent_error"
