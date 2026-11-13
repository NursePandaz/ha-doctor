"""Local, read-only Home Assistant diagnostics."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAME, OUTAGE_THRESHOLD, SCAN_INTERVAL
from .scanner import Report, async_scan

type DoctorEntry = ConfigEntry[DataUpdateCoordinator[Report | None]]
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: DoctorEntry) -> bool:
    """Start scanning once the rest of Home Assistant has loaded."""

    async def update() -> Report | None:
        if hass.state is not CoreState.running:
            return None
        return async_scan(hass, dt_util.utcnow())

    coordinator = entry.runtime_data = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        config_entry=entry,
        name=NAME,
        update_method=update,
        update_interval=SCAN_INTERVAL,
        always_update=False,
    )

    @callback
    def publish_issues() -> None:
        report = coordinator.data
        if report is None or not coordinator.last_update_success:
            return
        with ir.async_refresh_issues(hass, DOMAIN, config_entry_id=entry.entry_id):
            for entity in sorted(report.unavailable):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"unavailable:{entity}",
                    config_entry_id=entry.entry_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="unavailable",
                    translation_placeholders={
                        "entity": entity,
                        "minutes": str(int(OUTAGE_THRESHOLD.total_seconds() / 60)),
                    },
                )
            for source, target in sorted(report.missing):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"missing:{source}:{target}",
                    config_entry_id=entry.entry_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="missing",
                    translation_placeholders={"source": source, "target": target},
                )

    # Keep diagnostics running even when both count sensors are disabled.
    entry.async_on_unload(coordinator.async_add_listener(publish_issues))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def first_scan(_: HomeAssistant) -> None:
        await coordinator.async_refresh()

    entry.async_on_unload(async_at_started(hass, first_scan))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DoctorEntry) -> bool:
    """Unload our sensors and remove our notices."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    with ir.async_refresh_issues(hass, DOMAIN, config_entry_id=entry.entry_id):
        pass
    return True
