"""Nitaqat/Saudization compliance service."""
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus
from app.models.nitaqat import NitaqatConfig, NitaqatBand

logger = logging.getLogger(__name__)

# Default thresholds when no NitaqatConfig exists
_DEFAULT_THRESHOLDS = {
    "platinum": 40.0,
    "green_high": 26.0,
    "green_low": 17.0,
    "yellow": 6.0,
}


class NitaqatService:
    """Nitaqat band calculation, gap analysis, and what-if simulation."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _get_config(self) -> NitaqatConfig | None:
        result = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    async def _get_headcount(self) -> tuple[int, int]:
        """Returns (total_active, saudi_active)."""
        total = (await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )).scalar_one()

        saudi = (await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
                Employee.is_saudi.is_(True),
            )
        )).scalar_one()

        return total, saudi

    def _calculate_band(
        self, ratio: float, config: NitaqatConfig | None
    ) -> NitaqatBand:
        if config:
            thresholds = {
                "platinum": config.platinum_threshold,
                "green_high": config.green_high_threshold,
                "green_low": config.green_low_threshold,
                "yellow": config.yellow_threshold,
            }
        else:
            thresholds = _DEFAULT_THRESHOLDS

        if ratio >= thresholds["platinum"]:
            return NitaqatBand.platinum
        elif ratio >= thresholds["green_high"]:
            return NitaqatBand.green_high
        elif ratio >= thresholds["green_low"]:
            return NitaqatBand.green_low
        elif ratio >= thresholds["yellow"]:
            return NitaqatBand.yellow
        else:
            return NitaqatBand.red

    def _gap_analysis(
        self, total: int, saudi: int, config: NitaqatConfig | None
    ) -> dict:
        """How many Saudis needed to reach target / next band."""
        target_pct = config.target_saudization_pct if config else 26.0
        ratio = (saudi / total * 100) if total > 0 else 0

        # Saudis needed for target
        if total > 0:
            needed_for_target = max(0, int((target_pct / 100 * total) - saudi + 0.999))
        else:
            needed_for_target = 0

        # Current band and next band up
        band = self._calculate_band(ratio, config)

        NEXT_BAND_MAP = {
            NitaqatBand.red: NitaqatBand.yellow,
            NitaqatBand.yellow: NitaqatBand.green_low,
            NitaqatBand.green_low: NitaqatBand.green_high,
            NitaqatBand.green_high: NitaqatBand.platinum,
            NitaqatBand.platinum: None,
        }

        next_band_thresholds = {
            NitaqatBand.red: config.yellow_threshold if config else 6.0,
            NitaqatBand.yellow: config.green_low_threshold if config else 17.0,
            NitaqatBand.green_low: config.green_high_threshold if config else 26.0,
            NitaqatBand.green_high: config.platinum_threshold if config else 40.0,
            NitaqatBand.platinum: None,
        }

        next_threshold = next_band_thresholds.get(band)
        needed_for_next_band = 0
        if next_threshold and total > 0:
            needed_for_next_band = max(0, int((next_threshold / 100 * total) - saudi + 0.999))

        next_band = NEXT_BAND_MAP.get(band)
        return {
            "saudis_needed_for_target": needed_for_target,
            "target_pct": target_pct,
            "saudis_needed_for_next_band": needed_for_next_band,
            "next_band": next_band.value if next_band else None,
            "next_band_threshold": next_threshold,
        }

    async def get_current_status(self) -> dict:
        """Full Nitaqat status: ratio, band, gap analysis."""
        config = await self._get_config()
        total, saudi = await self._get_headcount()
        ratio = round((saudi / total * 100) if total > 0 else 0, 2)
        band = self._calculate_band(ratio, config)
        gap = self._gap_analysis(total, saudi, config)

        return {
            "total_employees": total,
            "saudi_employees": saudi,
            "non_saudi_employees": total - saudi,
            "saudization_ratio": ratio,
            "current_band": band.value,
            "gap_analysis": gap,
            "config": {
                "industry": config.industry if config else "general",
                "size_category": config.size_category.value if config else "small",
                "target_pct": config.target_saudization_pct if config else 26.0,
                "platinum_threshold": config.platinum_threshold if config else 40.0,
                "green_high_threshold": config.green_high_threshold if config else 26.0,
                "green_low_threshold": config.green_low_threshold if config else 17.0,
                "yellow_threshold": config.yellow_threshold if config else 6.0,
            },
        }

    async def simulate(
        self,
        hire_saudi: int = 0,
        hire_non_saudi: int = 0,
        terminate_saudi: int = 0,
        terminate_non_saudi: int = 0,
    ) -> dict:
        """What-if simulation: project new ratio and band after hypothetical changes."""
        config = await self._get_config()
        total, saudi = await self._get_headcount()

        if terminate_saudi > saudi:
            return {"error": "Cannot terminate more Saudi employees than currently exist", "current_saudi": saudi}
        if terminate_non_saudi > (total - saudi):
            return {"error": "Cannot terminate more non-Saudi employees than currently exist", "current_non_saudi": total - saudi}

        new_saudi = saudi + hire_saudi - terminate_saudi
        new_total = total + hire_saudi + hire_non_saudi - terminate_saudi - terminate_non_saudi

        if new_saudi < 0:
            new_saudi = 0
        if new_total < 0:
            new_total = 0

        current_ratio = round((saudi / total * 100) if total > 0 else 0, 2)
        new_ratio = round((new_saudi / new_total * 100) if new_total > 0 else 0, 2)

        current_band = self._calculate_band(current_ratio, config)
        new_band = self._calculate_band(new_ratio, config)

        band_order = [NitaqatBand.red, NitaqatBand.yellow, NitaqatBand.green_low,
                       NitaqatBand.green_high, NitaqatBand.platinum]
        band_change = "unchanged"
        if band_order.index(new_band) > band_order.index(current_band):
            band_change = "improved"
        elif band_order.index(new_band) < band_order.index(current_band):
            band_change = "degraded"

        return {
            "current": {
                "total": total, "saudi": saudi, "ratio": current_ratio,
                "band": current_band.value,
            },
            "simulated": {
                "total": new_total, "saudi": new_saudi, "ratio": new_ratio,
                "band": new_band.value,
            },
            "changes": {
                "hire_saudi": hire_saudi, "hire_non_saudi": hire_non_saudi,
                "terminate_saudi": terminate_saudi, "terminate_non_saudi": terminate_non_saudi,
            },
            "band_change": band_change,
            "gap_analysis": self._gap_analysis(new_total, new_saudi, config),
        }

    async def check_termination_impact(self, employee_id: uuid.UUID) -> dict:
        """Check if terminating a specific employee would cause a band drop.

        Called as an integration point when employee status changes.
        """
        config = await self._get_config()
        total, saudi = await self._get_headcount()

        # Look up the employee
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = result.scalar_one_or_none()
        if not emp:
            return {"warning": False, "reason": "Employee not found"}

        new_total = total - 1
        new_saudi = saudi - 1 if emp.is_saudi else saudi

        current_ratio = (saudi / total * 100) if total > 0 else 0
        new_ratio = (new_saudi / new_total * 100) if new_total > 0 else 0

        current_band = self._calculate_band(current_ratio, config)
        new_band = self._calculate_band(new_ratio, config)

        # Check if near target
        target_pct = config.target_saudization_pct if config else 26.0
        buffer = config.alert_buffer_pct if config else 2.0

        warning = False
        reasons = []

        if new_band != current_band:
            warning = True
            reasons.append(
                f"Nitaqat band will drop from {current_band.value} to {new_band.value}"
            )

        if new_ratio < target_pct and current_ratio >= target_pct:
            warning = True
            reasons.append(
                f"Saudization ratio will drop below target ({target_pct}%)"
            )

        if new_ratio < (target_pct - buffer):
            warning = True
            reasons.append(
                f"Saudization ratio will be {buffer}%+ below target"
            )

        return {
            "employee_id": str(employee_id),
            "employee_is_saudi": emp.is_saudi,
            "current_ratio": round(current_ratio, 2),
            "projected_ratio": round(new_ratio, 2),
            "current_band": current_band.value,
            "projected_band": new_band.value,
            "warning": warning,
            "reasons": reasons,
        }
