"""Counts-only diagnostic export for support."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import DoctorEntry
from .const import OUTAGE_THRESHOLD, SCAN_INTERVAL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DoctorEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    report = coordinator.data
    return {
        "interval_seconds": int(SCAN_INTERVAL.total_seconds()),
        "outage_threshold_seconds": int(OUTAGE_THRESHOLD.total_seconds()),
        "scan_status": (
            "failed"
            if not coordinator.last_update_success
            else "waiting"
            if report is None
            else "ok"
        ),
        "last_successful_counts": None
        if report is None
        else {
            "unavailable_entities": len(report.unavailable),
            "missing_references": len(report.missing),
        },
    }
