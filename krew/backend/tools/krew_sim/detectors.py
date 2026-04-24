"""Bug detectors — deterministic checks applied to each turn result."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .client import TurnResult
from .config import MAX_LATENCY_MS


@dataclass
class DetectorResult:
    detector: str
    passed: bool
    detail: str = ""


def _has_arabic(text: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF]', text))


def _has_english_words(text: str) -> bool:
    return bool(re.search(r'[a-zA-Z]{3,}', text))


# ── The 11 detectors ─────────────────────────────────────────

def language_consistency(turn: TurnResult, persona_language: str = "ar", **_) -> DetectorResult:
    """Response language should match persona language."""
    text = turn.response_text
    if not text:
        return DetectorResult("language_consistency", False, "Empty response")
    if persona_language == "ar":
        ok = _has_arabic(text)
        return DetectorResult("language_consistency", ok,
                              "Arabic persona got no Arabic in response" if not ok else "")
    else:
        ok = _has_english_words(text)
        return DetectorResult("language_consistency", ok,
                              "English persona got no English in response" if not ok else "")


def no_raw_enum(turn: TurnResult, **_) -> DetectorResult:
    """Response must not expose raw Python enum values."""
    patterns = [
        r'LeaveType\.\w+',
        r'LeaveStatus\.\w+',
        r'EmployeeStatus\.\w+',
        r'ConversationStatus\.\w+',
    ]
    for pat in patterns:
        match = re.search(pat, turn.response_text)
        if match:
            return DetectorResult("no_raw_enum", False, f"Raw enum found: {match.group()}")
    return DetectorResult("no_raw_enum", True)


def response_not_empty(turn: TurnResult, **_) -> DetectorResult:
    """Response must not be empty or whitespace-only."""
    ok = bool(turn.response_text and turn.response_text.strip())
    return DetectorResult("response_not_empty", ok,
                          "Empty or whitespace-only response" if not ok else "")


def no_500_error(turn: TurnResult, **_) -> DetectorResult:
    """HTTP status must not be 5xx."""
    ok = turn.status_code < 500
    return DetectorResult("no_500_error", ok,
                          f"Server error: HTTP {turn.status_code}" if not ok else "")


def correct_agent(turn: TurnResult, expected_agent: str | None = None, **_) -> DetectorResult:
    """Response should come from the expected agent."""
    if expected_agent is None:
        return DetectorResult("correct_agent", True, "No agent expectation set")
    ok = turn.agent == expected_agent
    return DetectorResult("correct_agent", ok,
                          f"Expected agent '{expected_agent}', got '{turn.agent}'" if not ok else "")


def response_contains_date(turn: TurnResult, **_) -> DetectorResult:
    """Response should contain at least one date."""
    patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{1,2}/\d{1,2}/\d{4}',
        r'\d{1,2}\s+(March|April|May|June|July|August|September|October|November|December|January|February)',
        r'(مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر|يناير|فبراير)',
        r'(الأحد|الاثنين|الثلاثاء|الأربعاء|الخميس|الجمعة|السبت)',
        r'(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)',
    ]
    for pat in patterns:
        if re.search(pat, turn.response_text, re.IGNORECASE):
            return DetectorResult("response_contains_date", True)
    return DetectorResult("response_contains_date", False, "No date found in response")


def mentions_balance(turn: TurnResult, **_) -> DetectorResult:
    """Response should mention a numeric balance or days."""
    patterns = [
        r'\d+\s*(day|days|يوم|أيام)',
        r'(balance|رصيد|متبقي|remaining)',
    ]
    for pat in patterns:
        if re.search(pat, turn.response_text, re.IGNORECASE):
            return DetectorResult("mentions_balance", True)
    return DetectorResult("mentions_balance", False, "No balance/days mention found")


def detects_duplicate(turn: TurnResult, **_) -> DetectorResult:
    """Response should indicate an overlapping or duplicate request."""
    patterns = [
        r'(overlap|duplicate|already|existing|تعارض|موجود|سابق|مكرر|متداخل)',
    ]
    for pat in patterns:
        if re.search(pat, turn.response_text, re.IGNORECASE):
            return DetectorResult("detects_duplicate", True)
    return DetectorResult("detects_duplicate", False, "No duplicate/overlap mention found")


def mentions_escalation(turn: TurnResult, **_) -> DetectorResult:
    """Response should mention escalation, human, or ticket."""
    patterns = [
        r'(escalat|human|specialist|مسؤول|أخصائي|تصعيد|ticket|تذكرة)',
    ]
    for pat in patterns:
        if re.search(pat, turn.response_text, re.IGNORECASE):
            return DetectorResult("mentions_escalation", True)
    return DetectorResult("mentions_escalation", False, "No escalation mention found")


def mentions_holiday(turn: TurnResult, **_) -> DetectorResult:
    """Response should mention a public holiday or that holidays are not deducted."""
    patterns = [
        r'(holiday|عطلة|إجازة رسمية|national day|اليوم الوطني|not (count|deduct)|لا (تحسب|تخصم))',
    ]
    for pat in patterns:
        if re.search(pat, turn.response_text, re.IGNORECASE):
            return DetectorResult("mentions_holiday", True)
    return DetectorResult("mentions_holiday", False, "No holiday mention found")


def latency(turn: TurnResult, **_) -> DetectorResult:
    """Response latency must be under threshold."""
    ok = turn.latency_ms <= MAX_LATENCY_MS
    return DetectorResult("latency", ok,
                          f"Latency {turn.latency_ms:.0f}ms exceeds {MAX_LATENCY_MS}ms" if not ok else
                          f"{turn.latency_ms:.0f}ms")


# ── Registry ─────────────────────────────────────────────────

DETECTOR_MAP: dict[str, callable] = {
    "language_consistency": language_consistency,
    "no_raw_enum": no_raw_enum,
    "response_not_empty": response_not_empty,
    "no_500_error": no_500_error,
    "correct_agent": correct_agent,
    "response_contains_date": response_contains_date,
    "mentions_balance": mentions_balance,
    "detects_duplicate": detects_duplicate,
    "mentions_escalation": mentions_escalation,
    "mentions_holiday": mentions_holiday,
    "latency": latency,
}
