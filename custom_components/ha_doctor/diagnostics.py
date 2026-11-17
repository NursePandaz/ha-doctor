"""Counts-only diagnostic export for support."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import DoctorEntry
from .const import Settings


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DoctorEntry
) -> dict[str, Any]:
    settings = Settings.from_options(entry.options)
    coordinator = entry.runtime_data
    report = coordinator.data
    return {
        "interval_seconds": settings.interval * 60,
        "outage_threshold_seconds": settings.threshold * 60,
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
