"""Exercise the installed custom component against real Home Assistant Core."""

import asyncio
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.ha_doctor.const import DOMAIN
from custom_components.ha_doctor.diagnostics import async_get_config_entry_diagnostics


def test_home_assistant_lifecycle(tmp_path):
    asyncio.run(asyncio.wait_for(exercise_instance(tmp_path), timeout=30))


async def exercise_instance(config_dir):
    """Start with static, dynamic, registered-only, and unregistered targets."""
    (config_dir / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components",
        target_is_directory=True,
    )
    hass = HomeAssistant(str(config_dir))
    loader.async_setup(hass)
    hass.config.skip_pip = True
    config = {
        "automation": [
            {
                "id": "night_lights",
                "alias": "Night lights",
                "triggers": [{"trigger": "event", "event_type": "unused_test_event"}],
                "actions": [
                    {
                        "action": "light.turn_on",
                        "target": {
                            "entity_id": ["light.renamed", "light.known", "light.lamp"]
                        },
                    }
                ],
            }
        ],
        "script": {
            "bedtime": {
                "sequence": [
                    {
                        "action": "light.turn_on",
                        "target": {"entity_id": "light.renamed"},
                    },
                    {
                        "action": "light.turn_off",
                        "target": {"entity_id": "light.renamed"},
                    },
                    {
                        "action": "light.turn_off",
                        "target": {"entity_id": "{{ chosen_light }}"},
                    },
                ]
            }
        },
    }
    hass.config_entries = config_entries.ConfigEntries(hass, config)
    try:
        assert await bootstrap.async_load_base_functionality(hass)
        assert await async_setup_component(hass, "automation", config)
        assert await async_setup_component(hass, "script", config)
        registry = er.async_get(hass)
        registry.async_get_or_create(
            "light",
            "test",
            "known",
            suggested_object_id="known",
            disabled_by=er.RegistryEntryDisabler.USER,
        )
        hass.states.async_set("light.lamp", "unavailable")
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert flow["type"] == "form"
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        entry = result["result"]
        assert entry.state is config_entries.ConfigEntryState.LOADED
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["scan_status"] == "waiting"

        await hass.async_start()
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert coordinator.data.missing == {
            ("automation.night_lights", "light.renamed"),
            ("script.bedtime", "light.renamed"),
        }
        assert not coordinator.data.unavailable
        assert (
            hass.states.get("sensor.ha_doctor_missing_entity_references").state == "2"
        )
        issues = ir.async_get(hass)
        issue_id = "missing:script.bedtime:light.renamed"
        issue = issues.async_get_issue(DOMAIN, issue_id)
        assert issue and not issue.is_fixable
        assert issue.translation_placeholders == {
            "source": "script.bedtime",
            "target": "light.renamed",
        }

        later = dt_util.utcnow() + timedelta(minutes=16)
        with patch("custom_components.ha_doctor.dt_util.utcnow", return_value=later):
            await coordinator.async_refresh()
        assert coordinator.data.unavailable == {"light.lamp"}
        assert issues.async_get_issue(DOMAIN, "unavailable:light.lamp")
        assert (
            hass.states.get("sensor.ha_doctor_persistently_unavailable_entities").state
            == "1"
        )
        assert await async_get_config_entry_diagnostics(hass, entry) == {
            "interval_seconds": 60,
            "outage_threshold_seconds": 900,
            "scan_status": "ok",
            "last_successful_counts": {
                "unavailable_entities": 1,
                "missing_references": 2,
            },
        }
        duplicate = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert duplicate["type"] == "abort"

        # A full recovery between scans restarts the continuous outage clock.
        hass.states.async_set("light.lamp", "on")
        hass.states.async_set("light.lamp", "unavailable")
        hass.states.async_set("light.renamed", "off")
        await coordinator.async_refresh()
        assert not coordinator.data.missing and not coordinator.data.unavailable
        assert issues.async_get_issue(DOMAIN, issue_id) is None
        assert issues.async_get_issue(DOMAIN, "unavailable:light.lamp") is None

        hass.states.async_remove("light.renamed")
        await coordinator.async_refresh()
        assert issues.async_get_issue(DOMAIN, issue_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert issues.async_get_issue(DOMAIN, issue_id) is None
        assert hass.states.get("light.lamp").state == "unavailable"
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert issues.async_get_issue(DOMAIN, issue_id)
    finally:
        await hass.async_stop(force=True)
