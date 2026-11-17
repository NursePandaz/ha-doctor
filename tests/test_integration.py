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

        # An upgrade may encounter individual notices from the previous version.
        old_id = "missing:script.bedtime:light.renamed"
        ir.async_create_issue(
            hass,
            DOMAIN,
            old_id,
            config_entry_id=entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing",
        )
        before_scan = await hass.config_entries.options.async_init(entry.entry_id)
        assert before_scan["step_id"] == "waiting"
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
        issue_id = "summary:missing"
        assert issues.async_get_issue(DOMAIN, old_id) is None
        issue = issues.async_get_issue(DOMAIN, issue_id)
        assert issue and not issue.is_fixable
        assert issue.translation_placeholders == {
            "count": "2",
        }

        later = dt_util.utcnow() + timedelta(minutes=16)
        with patch("custom_components.ha_doctor.dt_util.utcnow", return_value=later):
            await coordinator.async_refresh()
        assert coordinator.data.unavailable == {"light.lamp"}
        assert issues.async_get_issue(DOMAIN, "summary:unavailable")
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
        assert issues.async_get_issue(DOMAIN, "summary:unavailable") is None

        hass.states.async_remove("light.renamed")
        await coordinator.async_refresh()
        assert issues.async_get_issue(DOMAIN, issue_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert issues.async_get_issue(DOMAIN, issue_id) is None
        assert hass.states.get("light.lamp").state == "unavailable"
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert issues.async_get_issue(DOMAIN, issue_id)

        options = hass.config_entries.options

        async def open_menu():
            menu = await options.async_init(entry.entry_id)
            assert menu["type"] == "menu"
            return menu["flow_id"]

        async def choose(flow_id, page):
            return await options.async_configure(flow_id, {"next_step_id": page})

        flow_id = await open_menu()
        missing = await choose(flow_id, "missing")
        assert missing["step_id"] == "missing"
        assert "light.renamed" in missing["description_placeholders"]["items"]
        await choose(flow_id, "init")
        assert (await choose(flow_id, "unavailable"))["step_id"] == "unavailable_clear"
        await choose(flow_id, "init")
        await choose(flow_id, "advanced")
        settings = {
            "threshold": 30,
            "interval": 5,
            "individual": True,
            "excluded": ["light.lamp"],
        }
        invalid = await options.async_configure(flow_id, {**settings, "interval": 1.5})
        assert invalid["errors"] == {"base": "whole_minutes"}
        assert (await options.async_configure(flow_id, settings))[
            "type"
        ] == "create_entry"
        await hass.async_block_till_done()
        assert entry.options == settings
        assert entry.runtime_data.update_interval == timedelta(minutes=5)
        assert issues.async_get_issue(DOMAIN, issue_id) is None
        assert issues.async_get_issue(DOMAIN, "missing:script.bedtime:light.renamed")
        hass.states.async_set("sensor.freezer", "unavailable")
        now = dt_util.utcnow()
        with patch(
            "custom_components.ha_doctor.dt_util.utcnow",
            return_value=now + timedelta(minutes=16),
        ):
            await entry.runtime_data.async_refresh()
        assert not entry.runtime_data.data.unavailable
        with patch(
            "custom_components.ha_doctor.dt_util.utcnow",
            return_value=now + timedelta(minutes=31),
        ):
            await entry.runtime_data.async_refresh()
        assert entry.runtime_data.data.unavailable == {"sensor.freezer"}
        flow_id = await open_menu()
        await choose(flow_id, "advanced")
        await options.async_configure(
            flow_id, {**settings, "individual": False, "excluded": []}
        )
        await hass.async_block_till_done()
        assert issues.async_get_issue(DOMAIN, issue_id)
        assert (
            issues.async_get_issue(DOMAIN, "missing:script.bedtime:light.renamed")
            is None
        )
        for idx in range(15):
            hass.states.async_set(f"sensor.test_{idx}", "unavailable")
        with patch(
            "custom_components.ha_doctor.dt_util.utcnow",
            return_value=now + timedelta(minutes=31),
        ):
            await entry.runtime_data.async_refresh()
        assert "light.lamp" in entry.runtime_data.data.unavailable
        flow_id = await open_menu()
        page = await choose(flow_id, "unavailable")
        assert page["description_placeholders"]["end"] == "12"
        assert (await choose(flow_id, "next_page"))["description_placeholders"][
            "start"
        ] == "13"
        assert (await choose(flow_id, "previous_page"))[
            "description_placeholders"
        ] == page["description_placeholders"]
    finally:
        await hass.async_stop(force=True)
