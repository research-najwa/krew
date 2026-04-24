"""Entry point: python -m tools.krew_sim [options]

Usage:
    python -m tools.krew_sim                          # run all scenarios
    python -m tools.krew_sim --scenarios leave-happy-path,balance-check
    python -m tools.krew_sim --tags p0                # run only P0 scenarios
    python -m tools.krew_sim --base-url http://localhost:9000
"""
from __future__ import annotations

import argparse
import sys

from .client import KrewClient
from .config import BASE_URL
from .runner import run_simulation
from .reporter import print_summary, write_json_report


def main() -> int:
    parser = argparse.ArgumentParser(description="krew-sim: Krew conversation simulator")
    parser.add_argument("--base-url", default=BASE_URL, help="Krew API base URL")
    parser.add_argument("--scenarios", default=None, help="Comma-separated scenario IDs to run")
    parser.add_argument("--tags", default=None, help="Comma-separated tags to filter by")
    args = parser.parse_args()

    scenario_ids = args.scenarios.split(",") if args.scenarios else None
    tags = args.tags.split(",") if args.tags else None

    print(f"\n  krew-sim starting against {args.base_url}")
    print(f"  Scenarios: {scenario_ids or 'ALL'}")
    print(f"  Tags: {tags or 'ALL'}")

    client = KrewClient(base_url=args.base_url)
    try:
        report = run_simulation(client, scenario_ids=scenario_ids, tags=tags)
    finally:
        client.close()

    print_summary(report)
    report_path = write_json_report(report)

    return 0 if report.failed_scenarios == 0 and not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
