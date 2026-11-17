"""Set up a single local scanner."""

from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, NAME, Settings
from .scanner import Report


class DoctorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Confirm setup through Devices & services."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return DoctorOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})


PAGE_SIZE = 12


class DoctorOptionsFlow(OptionsFlowWithReload):
    """Read a local report or change scan preferences."""

    _rows: list[str]
    _page: int

    def _report(self) -> Report | None:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.last_update_success:
            return None
        return coordinator.data

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        report = self._report()
        if report is None:
            return self.async_show_menu(
                step_id="waiting", menu_options=["init", "advanced"]
            )
        return self.async_show_menu(
            step_id="init",
            menu_options=["missing", "unavailable", "advanced"],
            description_placeholders={
                "missing": str(len(report.missing)),
                "offline": str(len(report.unavailable)),
            },
        )

    def _entity_label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if (
            not state
            or not (name := state.attributes.get("friendly_name"))
            or not isinstance(name, str)
        ):
            return f"`{entity_id}`"
        # Keep user-defined names inside a single Markdown code span.
        label = " ".join(name.replace("`", "'").split())
        return f"`{label}` (`{entity_id}`)"

    async def async_step_missing(self, user_input=None) -> ConfigFlowResult:
        report = self._report()
        if report is None:
            return await self.async_step_init()
        self._rows = [
            f"- {self._entity_label(source)} → `{target}`"
            for source, target in sorted(report.missing)
        ]
        self._page = 0
        self._category = "missing"
        return self._show_page()

    async def async_step_unavailable(self, user_input=None) -> ConfigFlowResult:
        report = self._report()
        if report is None:
            return await self.async_step_init()
        self._rows = [
            f"- {self._entity_label(entity)}" for entity in sorted(report.unavailable)
        ]
        self._page = 0
        self._category = "unavailable"
        return self._show_page()

    # HA validates the step behind each menu, including its empty-state variant.
    async_step_waiting = async_step_init
    async_step_missing_clear = async_step_missing
    async_step_unavailable_clear = async_step_unavailable

    def _show_page(self) -> ConfigFlowResult:
        if not self._rows:
            return self.async_show_menu(
                step_id=f"{self._category}_clear", menu_options=["init"]
            )
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(self._rows))
        choices = []
        if end < len(self._rows):
            choices.append("next_page")
        if start:
            choices.append("previous_page")
        return self.async_show_menu(
            step_id=self._category,
            menu_options=[*choices, "init"],
            description_placeholders={
                "start": str(start + 1),
                "end": str(end),
                "total": str(len(self._rows)),
                "items": "\n".join(self._rows[start:end]),
            },
        )

    async def async_step_next_page(self, user_input=None) -> ConfigFlowResult:
        self._page += 1
        return self._show_page()

    async def async_step_previous_page(self, user_input=None) -> ConfigFlowResult:
        self._page -= 1
        return self._show_page()

    async def async_step_advanced(self, user_input=None) -> ConfigFlowResult:
        current = Settings.from_options(self.config_entry.options)
        errors = {}
        if user_input is not None:
            if all(user_input[key].is_integer() for key in ("interval", "threshold")):
                return self.async_create_entry(
                    title="",
                    data={
                        **user_input,
                        "interval": int(user_input["interval"]),
                        "threshold": int(user_input["threshold"]),
                    },
                )
            errors["base"] = "whole_minutes"

        def minutes(maximum: int) -> selector.NumberSelector:
            return selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=maximum,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            )

        schema = probatio.Schema(
            {
                probatio.Required("threshold", default=current.threshold): minutes(
                    1440
                ),
                probatio.Required("interval", default=current.interval): minutes(60),
                probatio.Optional("excluded", default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                probatio.Required(
                    "individual", default=current.individual
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input
                if user_input is not None
                else {"excluded": sorted(current.excluded)},
            ),
            errors=errors,
        )
