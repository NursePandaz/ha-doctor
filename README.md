# HA Doctor

HA Doctor checks your Home Assistant once a minute and explains what needs attention in **Settings → System → Repairs**. It runs locally. You decide whether to change a device, automation, or script.

| Finding | What triggers it | Where to look first |
| --- | --- | --- |
| Persistently unavailable entity | An entity has continuously reported `unavailable` for at least 15 minutes. | Open its device page. If several entities on one device are down, check power and connectivity. If several devices from the same integration are down, check the integration. |
| Missing entity reference | A loaded automation or script refers to a specific entity ID that is absent from both current states and the entity registry. | Open the named automation or script. Look for the reported ID and check whether its entity was renamed, removed, or has yet to load. |

For example, if both your bedtime script and your evening lights automation refer to `light.old_porch`, you get two findings. Each names the source to inspect. When the reference becomes valid or you remove it and reload the edited source, the next scan clears the corresponding warning.

## Install the private preview

Requires **Home Assistant Core 2026.11.1 or newer**. The test suite targets 2026.11.1.

1. While signed in to GitHub with repository access, download and unzip the source from **Code → Download ZIP**.
2. Copy the entire `custom_components/ha_doctor` folder into the `custom_components` directory beside your `configuration.yaml`. Create that directory if necessary. The installed manifest should be at `custom_components/ha_doctor/manifest.json`.
3. Restart Home Assistant. Open **Settings → Devices & services → Add integration**, search for **HA Doctor**, and confirm setup.
4. Open the HA Doctor device to see **Persistently unavailable entities** and **Missing entity references**. Add either sensor to a dashboard if you want a running count. Open **Settings → System → Repairs** for individual findings.

To try it without interrupting a device, save a temporary script with a light action targeting an unused literal ID such as `light.ha_doctor_example_missing`. Leave the script unexecuted. Within the next scan, a warning should name your script and the missing light. Delete the test script and the warning should clear within another scan.

To uninstall, remove the HA Doctor entry in **Devices & services**, delete its folder from `custom_components`, and restart Home Assistant.

## What the scan covers

- Scanning starts after Home Assistant finishes starting. The outage timer uses the entity's most recent state change. A recovery between scans resets the timer. Restarting Home Assistant can reset the available outage history.
- The outage check skips unknown states, restored placeholders, disabled entries, and HA Doctor's own sensors. An intentionally offline device can still be reported.
- The reference check uses Home Assistant's indexed entity relationships for loaded automations and scripts. A registered target counts as known even when disabled. Multiple mentions of the same target in one source count once.
- Dynamically computed targets, dashboards, device and area targets, invalid configurations that failed to load, and templates outside the reference index are outside the scan's coverage.
- HA Doctor creates its own sensors and informational Repairs warnings. It never executes an automation, rewrites YAML, removes an entity, or applies a repair.
- Choose **Download diagnostics** from the integration entry menu for support. HA Doctor's portion contains scan status, timing settings, and counts. Home Assistant adds its standard system metadata. Entity IDs are shown locally in Repairs.

## HACS and Marketplace

Private preview users install manually. Once the repository is public, it can be added as a custom repository using the GitHub URL and the **Integration** category. Catalog inclusion also requires passing HACS validation and hassfest, a full GitHub release, and a reviewed submission. The workflow enables HACS validation on public visibility. [Marketplace integration guide](https://contributors.home-assistant.io/marketplace/guides/integrations/) · [Catalog submission](https://contributors.home-assistant.io/marketplace/guides/catalog/) · [HACS repository requirements](https://www.hacs.xyz/docs/publish/start/)

## Development

Use Python 3.14.2 or newer in the 3.14 series. From the repository root:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
ruff check .
ruff format --check .
```

The lifecycle test starts Home Assistant Core in a temporary configuration directory. It loads a real automation and script, adds HA Doctor through its config flow, checks warnings and recovery, and unloads and reloads the integration. The outage boundary tests use state timestamps, so the suite runs without waiting 15 minutes.

Licensed under the [MIT License](LICENSE).
