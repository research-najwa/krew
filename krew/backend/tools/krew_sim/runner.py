"""Scenario runner — executes scenarios and collects results."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from .client import KrewClient, TurnResult
from .personas import Persona, ALL_PERSONAS, resolve_personas
from .scenarios import Scenario, ALL_SCENARIOS
from .detectors import DETECTOR_MAP, DetectorResult


@dataclass
class TurnReport:
    scenario_id: str
    turn_number: int
    persona: str
    message_sent: str
    description: str
    agent: str
    response_text: str
    status_code: int
    latency_ms: float
    error: str | None
    detector_results: list[dict]
    expect_contains_results: list[dict]
    expect_not_contains_results: list[dict]
    passed: bool


@dataclass
class ScenarioReport:
    scenario_id: str
    scenario_name: str
    persona: str
    tags: list[str]
    turns: list[TurnReport]
    passed: bool


@dataclass
class SimulationReport:
    scenarios: list[ScenarioReport] = field(default_factory=list)
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    total_turns: int = 0
    passed_turns: int = 0
    failed_turns: int = 0
    errors: list[str] = field(default_factory=list)


def _find_persona(name: str) -> Persona | None:
    for p in ALL_PERSONAS:
        if p.name == name:
            return p
    return None


def run_simulation(
    client: KrewClient,
    scenario_ids: list[str] | None = None,
    tags: list[str] | None = None,
) -> SimulationReport:
    """Run all (or filtered) scenarios and return a full report."""

    employees = client.list_employees()
    if not employees:
        report = SimulationReport()
        report.errors.append("Could not fetch employees from /api/v1/chat/employees. Is the server running?")
        return report

    try:
        resolve_personas(employees)
    except RuntimeError as e:
        report = SimulationReport()
        report.errors.append(str(e))
        return report

    scenarios = ALL_SCENARIOS
    if scenario_ids:
        scenarios = [s for s in scenarios if s.id in scenario_ids]
    if tags:
        scenarios = [s for s in scenarios if any(t in s.tags for t in tags)]

    report = SimulationReport()

    for scenario in scenarios:
        persona = _find_persona(scenario.persona_name)
        if not persona:
            report.errors.append(f"Persona '{scenario.persona_name}' not found for scenario '{scenario.id}'")
            continue

        if not persona.employee_id:
            report.errors.append(f"Persona '{persona.name}' has no resolved employee_id")
            continue

        if scenario.reset_before:
            client.reset_conversation(persona.employee_id)

        sys.stdout.write(f"\n  Running: {scenario.name} [{scenario.id}]\n")
        sys.stdout.flush()

        turn_reports: list[TurnReport] = []
        scenario_passed = True

        for i, turn in enumerate(scenario.turns, start=1):
            sys.stdout.write(f"    Turn {i}: {turn.description or turn.message[:50]}...")
            sys.stdout.flush()

            result: TurnResult = client.send_message(
                employee_id=persona.employee_id,
                message=turn.message,
                turn_number=i,
            )

            detector_results: list[dict] = []
            for det_name in turn.detectors:
                fn = DETECTOR_MAP.get(det_name)
                if not fn:
                    detector_results.append({"detector": det_name, "passed": False, "detail": "Unknown detector"})
                    continue
                kwargs = {
                    "persona_language": persona.language,
                    "expected_agent": turn.expected_agent,
                }
                dr: DetectorResult = fn(result, **kwargs)
                detector_results.append({"detector": dr.detector, "passed": dr.passed, "detail": dr.detail})

            contains_results = []
            for sub in turn.expect_contains:
                found = sub.lower() in result.response_text.lower()
                contains_results.append({"substring": sub, "found": found})

            not_contains_results = []
            for sub in turn.expect_not_contains:
                found = sub.lower() in result.response_text.lower()
                not_contains_results.append({"substring": sub, "found": found})

            turn_passed = (
                all(d["passed"] for d in detector_results)
                and all(c["found"] for c in contains_results)
                and all(not c["found"] for c in not_contains_results)
                and result.error is None
            )

            if not turn_passed:
                scenario_passed = False

            status_icon = "PASS" if turn_passed else "FAIL"
            sys.stdout.write(f" {status_icon} ({result.latency_ms:.0f}ms)\n")
            sys.stdout.flush()

            turn_reports.append(TurnReport(
                scenario_id=scenario.id,
                turn_number=i,
                persona=persona.name,
                message_sent=turn.message,
                description=turn.description,
                agent=result.agent,
                response_text=result.response_text[:500],
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                error=result.error,
                detector_results=detector_results,
                expect_contains_results=contains_results,
                expect_not_contains_results=not_contains_results,
                passed=turn_passed,
            ))

            report.total_turns += 1
            if turn_passed:
                report.passed_turns += 1
            else:
                report.failed_turns += 1

        scenario_report = ScenarioReport(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            persona=persona.name,
            tags=scenario.tags,
            turns=turn_reports,
            passed=scenario_passed,
        )
        report.scenarios.append(scenario_report)
        report.total_scenarios += 1
        if scenario_passed:
            report.passed_scenarios += 1
        else:
            report.failed_scenarios += 1

    return report
