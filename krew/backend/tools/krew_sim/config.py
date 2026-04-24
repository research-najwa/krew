"""Configuration for krew-sim."""
import os
from pathlib import Path

# Server
BASE_URL = os.environ.get("KREW_SIM_BASE_URL", "http://localhost:8000")
API_PREFIX = "/api/v1/chat"
TIMEOUT_SECONDS = float(os.environ.get("KREW_SIM_TIMEOUT", "30"))

# Output
REPORT_DIR = Path(os.environ.get(
    "KREW_SIM_REPORT_DIR",
    str(Path(__file__).resolve().parents[2] / "test-reports")
))

# Thresholds
MAX_LATENCY_MS = 10_000  # 10 seconds per turn
