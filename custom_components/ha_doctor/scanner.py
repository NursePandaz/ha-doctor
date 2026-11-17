"""Inspect live state and the references indexed by Home Assistant."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.automation import entities_in_automation
from homeassistant.components.script import entities_in_script
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State, callback, valid_entity_id
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, Settings


@dataclass(frozen=True)
class Report:
    """One snapshot. Count missing references once per source and target."""

    unavailable: frozenset[str]
    missing: frozenset[tuple[str, str]]


def is_persistent_outage(state: State, now: datetime, threshold: timedelta) -> bool:
    """Using last_changed catches recoveries even between two scans."""
    return (
        state.state == STATE_UNAVAILABLE
        and not state.attributes.get(ATTR_RESTORED)
        and now - state.last_changed >= threshold
    )


@callback
def async_scan(hass: HomeAssistant, now: datetime, settings: Settings) -> Report:
    """Read one consistent snapshot on the Home Assistant event loop."""
    registry = er.async_get(hass)
    unavailable = set()
    duration = settings.outage_duration
    for state in hass.states.async_all():
        if state.entity_id in settings.excluded or not is_persistent_outage(
            state, now, duration
        ):
            continue
        entry = registry.async_get(state.entity_id)
        if entry and (entry.disabled or entry.platform == DOMAIN):
            continue
        unavailable.add(state.entity_id)

    missing = set()
    for domain, get_references in (
        ("automation", entities_in_automation),
        ("script", entities_in_script),
    ):
        for source in hass.states.async_entity_ids(domain):
            for target in get_references(hass, source):
                if (
                    isinstance(target, str)
                    and valid_entity_id(target)
                    and hass.states.get(target) is None
                    and registry.async_get(target) is None
                ):
                    missing.add((source, target))
    return Report(frozenset(unavailable), frozenset(missing))
