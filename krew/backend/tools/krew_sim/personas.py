"""Employee personas for simulation.

Each persona maps to a seed-data employee. The `employee_id` is resolved
at runtime by matching on `employee_number` via GET /chat/employees.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Persona:
    name: str
    employee_number: str  # matched at runtime to get UUID
    employee_id: str = ""  # resolved at runtime
    language: str = "ar"
    description: str = ""
    traits: list[str] | None = None


AHMED = Persona(
    name="Ahmed (Arabic senior)",
    employee_number="EMP-001",
    language="ar",
    description="Senior VP, Arabic speaker, tests normal leave flows and manager-level features",
    traits=["uses Saudi dialect", "concise", "expects fast answers"],
)

SARA = Persona(
    name="Sara (English new hire)",
    employee_number="EMP-004",
    language="ar",
    description="Recent hire, tests onboarding-adjacent questions and basic leave flows",
    traits=["polite", "asks follow-up questions", "sometimes unsure of process"],
)

FATIMAH = Persona(
    name="Fatimah (Arabic, HR manager, maternity-eligible)",
    employee_number="EMP-002",
    language="ar",
    description="Female HR manager, tests maternity leave and policy questions",
    traits=["formal Arabic", "knows HR terminology", "expects empathy"],
)

KHALID = Persona(
    name="Khalid (Arabic developer)",
    employee_number="EMP-005",
    language="ar",
    description="Developer, tests team calendar and cross-agent routing",
    traits=["casual dialect", "sometimes mixes AR/EN tech terms"],
)

OMAR = Persona(
    name="Omar (English expat)",
    employee_number="EMP-003",
    language="en",
    description="Non-Saudi remote worker, English speaker, tests English flows and expat-specific cases",
    traits=["formal English", "references Iqama", "asks about international transfers"],
)

ADVERSARIAL = Persona(
    name="Adversarial tester",
    employee_number="EMP-001",  # reuses Ahmed's account
    language="ar",
    description="Tries to break the system with injection, gibberish, contradictions",
    traits=["sends gibberish", "prompt injection", "contradicts self", "sends empty-ish messages"],
)


ALL_PERSONAS = [AHMED, SARA, FATIMAH, KHALID, OMAR, ADVERSARIAL]


def resolve_personas(employees: list[dict]) -> None:
    """Match personas to employee UUIDs from the /chat/employees response."""
    emp_map = {e["employee_number"]: e["id"] for e in employees}
    for persona in ALL_PERSONAS:
        if persona.employee_number in emp_map:
            persona.employee_id = emp_map[persona.employee_number]
        else:
            raise RuntimeError(
                f"Persona '{persona.name}' needs employee_number={persona.employee_number} "
                f"but it was not found in the database. Available: {list(emp_map.keys())}"
            )
