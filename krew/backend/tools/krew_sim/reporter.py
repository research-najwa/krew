"""Report generation — terminal summary + JSON file."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .config import REPORT_DIR
from .runner import SimulationReport


def print_summary(report: SimulationReport) -> None:
    """Print a compact terminal summary."""
    print("\n" + "=" * 64)
    print("  KREW-SIM RESULTS")
    print("=" * 64)

    if report.errors:
        print("\n  ERRORS:")
        for err in report.errors:
            print(f"    - {err}")

    print(f"\n  Scenarios: {report.passed_scenarios}/{report.total_scenarios} passed")
    print(f"  Turns:     {report.passed_turns}/{report.total_turns} passed")

    failed = [s for s in report.scenarios if not s.passed]
    if failed:
        print(f"\n  FAILURES ({len(failed)}):")
        for s in failed:
            print(f"\n    [{s.scenario_id}] {s.scenario_name}")
            for t in s.turns:
                if not t.passed:
                    print(f"      Turn {t.turn_number}: {t.description}")
                    if t.error:
                        print(f"        Error: {t.error}")
                    for d in t.detector_results:
                        if not d["passed"]:
                            print(f"        FAIL [{d['detector']}]: {d['detail']}")
                    for c in t.expect_contains_results:
                        if not c["found"]:
                            print(f"        FAIL [expect_contains]: '{c['substring']}' not found")
                    for c in t.expect_not_contains_results:
                        if c["found"]:
                            print(f"        FAIL [expect_not_contains]: '{c['substring']}' was found")

    print("\n" + "=" * 64)


def write_json_report(report: SimulationReport) -> Path:
    """Write the full report to a JSON file."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = REPORT_DIR / f"krew_sim_{timestamp}.json"

    data = asdict(report)
    data["generated_at"] = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  Report written to: {filepath}")
    return filepath
