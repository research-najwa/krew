"""Orchestrator routing tests -- strong-override behavior.

Verifies that when the user has an explicit current_agent (sidebar selection),
a clear cross-domain intent in the message correctly overrides the sticky
selection, while ambiguous or empty intents preserve the user's choice.

These tests mock only what the orchestrator's `route()` method actually touches,
so no DB or Anthropic client is required.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest

# Test-safe env BEFORE importing app modules (matches test_ws_chat.py pattern)
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRY_HOURS", "24")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.agents.orchestrator import AgentOrchestrator  # noqa: E402


@pytest.fixture
def orchestrator() -> AgentOrchestrator:
    """Orchestrator with a mocked DB session -- route() never hits it directly
    when employee_id is None (access checks are skipped)."""
    db = MagicMock()
    tenant_id = uuid.uuid4()
    return AgentOrchestrator(db=db, tenant_id=tenant_id)


class TestStrongOverride:
    """Rule 4: strong keyword intent overrides sticky current_agent."""

    @pytest.mark.asyncio
    async def test_leave_request_overrides_ahmad(self, orchestrator):
        """Bug repro: user has Ahmad selected, asks to apply for leave.

        'apply for annual leave' hits 3 deema keywords (apply, annual, leave),
        which is >= STRONG_OVERRIDE_THRESHOLD, so it must route to deema
        instead of being trapped inside Ahmad's context.
        """
        agent, _, err = await orchestrator.route(
            message="apply for annual leave",
            current_agent="ahmad",
        )
        assert err is None
        assert agent == "deema"

    @pytest.mark.asyncio
    async def test_hire_candidate_overrides_deema(self, orchestrator):
        """User in Deema context asks to hire someone -- should route to Mohammad.

        'hire a new candidate' hits 2 mohammad keywords (hire, candidate).
        """
        agent, _, err = await orchestrator.route(
            message="hire a new candidate",
            current_agent="deema",
        )
        assert err is None
        assert agent == "mohammad"


class TestHighSignalOverride:
    """HIGH_SIGNAL keywords score 2 each, so a single match is enough to
    override a sticky current_agent. This unblocks short cross-domain
    messages like 'build agent' that previously scored only 1."""

    @pytest.mark.asyncio
    async def test_build_agent_overrides_deema(self, orchestrator):
        """'build agent' in Deema context must route to Yara."""
        agent, _, err = await orchestrator.route(
            message="build agent",
            current_agent="deema",
        )
        assert err is None
        assert agent == "yara"

    @pytest.mark.asyncio
    async def test_design_agent_overrides_deema(self, orchestrator):
        """'design agent for finance' in Deema context must route to Yara."""
        agent, _, err = await orchestrator.route(
            message="design agent for finance",
            current_agent="deema",
        )
        assert err is None
        assert agent == "yara"

    @pytest.mark.asyncio
    async def test_hire_someone_overrides_ahmad(self, orchestrator):
        """'hire someone' in Ahmad context must route to Mohammad."""
        agent, _, err = await orchestrator.route(
            message="hire someone",
            current_agent="ahmad",
        )
        assert err is None
        assert agent == "mohammad"

    @pytest.mark.asyncio
    async def test_onboard_new_overrides_deema(self, orchestrator):
        """'onboard new engineer' in Deema context must route to Waleed."""
        agent, _, err = await orchestrator.route(
            message="onboard new engineer",
            current_agent="deema",
        )
        assert err is None
        assert agent == "waleed"

    @pytest.mark.asyncio
    async def test_compliance_audit_overrides_mohammad(self, orchestrator):
        """'compliance audit' in Mohammad context must route to Ahmad."""
        agent, _, err = await orchestrator.route(
            message="compliance audit",
            current_agent="mohammad",
        )
        assert err is None
        assert agent == "ahmad"


class TestStickyPreserved:
    """Rule 5: weak/empty intent preserves the user's sidebar selection."""

    @pytest.mark.asyncio
    async def test_greeting_stays_with_ahmad(self, orchestrator):
        """'hi how are you' has zero keyword matches -- stay put."""
        agent, _, err = await orchestrator.route(
            message="hi how are you",
            current_agent="ahmad",
        )
        assert err is None
        assert agent == "ahmad"

    @pytest.mark.asyncio
    async def test_single_keyword_does_not_override(self, orchestrator):
        """'what's my balance' (from current_agent=mohammad) hits only one
        deema keyword (balance). Score 1 is BELOW the override threshold,
        so the explicit mohammad selection is preserved.
        """
        agent, _, err = await orchestrator.route(
            message="what's my balance",
            current_agent="mohammad",
        )
        assert err is None
        assert agent == "mohammad"


class TestMentionWins:
    """Rules 1-2 (@mention) must still beat the strong-override path."""

    @pytest.mark.asyncio
    async def test_mention_beats_current_agent(self, orchestrator):
        """Explicit @deema mention routes to deema even with current_agent=ahmad."""
        agent, cleaned, err = await orchestrator.route(
            message="@deema leave balance",
            current_agent="ahmad",
        )
        assert err is None
        assert agent == "deema"
        assert "@deema" not in cleaned

    @pytest.mark.asyncio
    async def test_mention_to_mohammad_beats_leave_keywords(self, orchestrator):
        """Even if the message has strong deema keywords, an explicit mention
        to mohammad wins (mentions are rule 1, highest priority)."""
        agent, _, err = await orchestrator.route(
            message="@mohammad apply for annual leave policy review",
            current_agent="ahmad",
        )
        assert err is None
        assert agent == "mohammad"
