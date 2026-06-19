"""Config flow for Battery Sizing Simulator."""

from __future__ import annotations

import logging
from typing import Any, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CHEMISTRY_LFP,
    CHEMISTRY_NMC,
    CHEMISTRY_CUSTOM,
    CHEMISTRY_PRESETS,
    CONF_GRID_EXPORT_SENSOR,
    CONF_GRID_IMPORT_SENSOR,
    CONF_CAPACITY_MIN,
    CONF_CAPACITY_MAX,
    CONF_CAPACITY_STEP,
    CONF_EFFICIENCY_CHARGE,
    CONF_EFFICIENCY_DISCHARGE,
    CONF_MAX_DOD,
    CONF_SELF_DISCHARGE_DAILY,
    CONF_BATTERY_CHEMISTRY,
    CONF_INJECTION_TARIFF,
    CONF_OFFTAKE_TARIFF_DAY,
    CONF_OFFTAKE_TARIFF_NIGHT,
    CONF_DAY_START_HOUR,
    CONF_DAY_END_HOUR,
    CONF_BATTERY_COST_PER_KWH,
    CONF_BATTERY_LIFESPAN,
    CONF_ANNUAL_DEGRADATION,
    CONF_DISCOUNT_RATE,
    CONF_RESERVE_CAPACITY,
    CONF_ENABLE_PEAK_SHAVING,
    CONF_PEAK_THRESHOLD_KW,
    CONF_ELECTRICITY_PRICE_INFLATION,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_CAPACITY_MIN,
    DEFAULT_CAPACITY_MAX,
    DEFAULT_CAPACITY_STEP,
    DEFAULT_EFFICIENCY_CHARGE,
    DEFAULT_EFFICIENCY_DISCHARGE,
    DEFAULT_MAX_DOD,
    DEFAULT_SELF_DISCHARGE_DAILY,
    DEFAULT_BATTERY_CHEMISTRY,
    DEFAULT_INJECTION_TARIFF,
    DEFAULT_OFFTAKE_TARIFF_DAY,
    DEFAULT_OFFTAKE_TARIFF_NIGHT,
    DEFAULT_DAY_START_HOUR,
    DEFAULT_DAY_END_HOUR,
    DEFAULT_BATTERY_COST_PER_KWH,
    DEFAULT_BATTERY_LIFESPAN,
    DEFAULT_ANNUAL_DEGRADATION,
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_RESERVE_CAPACITY,
    DEFAULT_ENABLE_PEAK_SHAVING,
    DEFAULT_PEAK_THRESHOLD_KW,
    DEFAULT_ELECTRICITY_PRICE_INFLATION,
    DEFAULT_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

STEP_SENSORS = "sensors"
STEP_BATTERY = "battery"
STEP_FINANCIAL = "financial"
STEP_ADVANCED = "advanced"


class BatterySizingSimulatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Battery Sizing Simulator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Step 1: Select grid export/import sensors."""
        return await self.async_step_sensors(user_input)

    async def async_step_sensors(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Step 1: Select grid sensors."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()

        schema = vol.Schema({
            vol.Required(CONF_GRID_EXPORT_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_GRID_IMPORT_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id=STEP_SENSORS,
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "info": (
                    "Select your grid export (injection) and import (offtake) sensors. "
                    "These must have long-term statistics enabled in HA recorder."
                )
            },
        )

    async def async_step_battery(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Step 2: Battery physical parameters."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Apply chemistry preset if not custom
            chemistry = user_input.get(CONF_BATTERY_CHEMISTRY, CHEMISTRY_LFP)
            if chemistry in CHEMISTRY_PRESETS:
                preset = CHEMISTRY_PRESETS[chemistry]
                user_input.setdefault(CONF_EFFICIENCY_CHARGE, preset["efficiency_charge"])
                user_input.setdefault(CONF_EFFICIENCY_DISCHARGE, preset["efficiency_discharge"])
                user_input.setdefault(CONF_MAX_DOD, preset["max_dod"])
                user_input.setdefault(CONF_SELF_DISCHARGE_DAILY, preset["self_discharge_daily"])
                user_input.setdefault(CONF_ANNUAL_DEGRADATION, preset["annual_degradation"])

            self._data.update(user_input)
            return await self.async_step_financial()

        schema = vol.Schema({
            vol.Required(CONF_BATTERY_CHEMISTRY, default=DEFAULT_BATTERY_CHEMISTRY): vol.In(
                [CHEMISTRY_LFP, CHEMISTRY_NMC, CHEMISTRY_CUSTOM]
            ),
            vol.Required(CONF_CAPACITY_MIN, default=DEFAULT_CAPACITY_MIN): vol.Coerce(float),
            vol.Required(CONF_CAPACITY_MAX, default=DEFAULT_CAPACITY_MAX): vol.Coerce(float),
            vol.Required(CONF_CAPACITY_STEP, default=DEFAULT_CAPACITY_STEP): vol.Coerce(float),
            vol.Required(CONF_MAX_DOD, default=DEFAULT_MAX_DOD): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=1.0)
            ),
            vol.Required(CONF_EFFICIENCY_CHARGE, default=DEFAULT_EFFICIENCY_CHARGE): vol.All(
                vol.Coerce(float), vol.Range(min=0.7, max=1.0)
            ),
            vol.Required(CONF_EFFICIENCY_DISCHARGE, default=DEFAULT_EFFICIENCY_DISCHARGE): vol.All(
                vol.Coerce(float), vol.Range(min=0.7, max=1.0)
            ),
            vol.Required(CONF_SELF_DISCHARGE_DAILY, default=DEFAULT_SELF_DISCHARGE_DAILY): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=0.01)
            ),
            vol.Required(CONF_RESERVE_CAPACITY, default=DEFAULT_RESERVE_CAPACITY): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=0.5)
            ),
        })

        return self.async_show_form(
            step_id=STEP_BATTERY,
            data_schema=schema,
            errors=errors,
        )

    async def async_step_financial(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Step 3: Financial parameters."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_advanced()

        schema = vol.Schema({
            vol.Required(CONF_INJECTION_TARIFF, default=DEFAULT_INJECTION_TARIFF): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=1.0)
            ),
            vol.Required(CONF_OFFTAKE_TARIFF_DAY, default=DEFAULT_OFFTAKE_TARIFF_DAY): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=2.0)
            ),
            vol.Required(CONF_OFFTAKE_TARIFF_NIGHT, default=DEFAULT_OFFTAKE_TARIFF_NIGHT): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=2.0)
            ),
            vol.Required(CONF_DAY_START_HOUR, default=DEFAULT_DAY_START_HOUR): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=23)
            ),
            vol.Required(CONF_DAY_END_HOUR, default=DEFAULT_DAY_END_HOUR): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=23)
            ),
            vol.Required(CONF_BATTERY_COST_PER_KWH, default=DEFAULT_BATTERY_COST_PER_KWH): vol.All(
                vol.Coerce(float), vol.Range(min=100.0, max=2000.0)
            ),
            vol.Required(CONF_BATTERY_LIFESPAN, default=DEFAULT_BATTERY_LIFESPAN): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=30)
            ),
            vol.Required(CONF_ANNUAL_DEGRADATION, default=DEFAULT_ANNUAL_DEGRADATION): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=0.1)
            ),
            vol.Required(CONF_DISCOUNT_RATE, default=DEFAULT_DISCOUNT_RATE): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=0.2)
            ),
            vol.Required(
                CONF_ELECTRICITY_PRICE_INFLATION, default=DEFAULT_ELECTRICITY_PRICE_INFLATION
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=0.2)),
        })

        return self.async_show_form(
            step_id=STEP_FINANCIAL,
            data_schema=schema,
            errors=errors,
        )

    async def async_step_advanced(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Step 4: Advanced / peak shaving options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Battery Sizing Simulator",
                data=self._data,
            )

        schema = vol.Schema({
            vol.Required(CONF_ENABLE_PEAK_SHAVING, default=DEFAULT_ENABLE_PEAK_SHAVING): bool,
            vol.Required(CONF_PEAK_THRESHOLD_KW, default=DEFAULT_PEAK_THRESHOLD_KW): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=20.0)
            ),
            vol.Required(CONF_SCAN_INTERVAL_HOURS, default=DEFAULT_SCAN_INTERVAL_HOURS): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=168)
            ),
        })

        return self.async_show_form(
            step_id=STEP_ADVANCED,
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return BatterySizingSimulatorOptionsFlow(config_entry)


class BatterySizingSimulatorOptionsFlow(config_entries.OptionsFlow):
    """Options flow to reconfigure after initial setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options - one combined form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data

        schema = vol.Schema({
            vol.Required(
                CONF_INJECTION_TARIFF, default=current.get(CONF_INJECTION_TARIFF, DEFAULT_INJECTION_TARIFF)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Required(
                CONF_OFFTAKE_TARIFF_DAY, default=current.get(CONF_OFFTAKE_TARIFF_DAY, DEFAULT_OFFTAKE_TARIFF_DAY)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
            vol.Required(
                CONF_OFFTAKE_TARIFF_NIGHT, default=current.get(CONF_OFFTAKE_TARIFF_NIGHT, DEFAULT_OFFTAKE_TARIFF_NIGHT)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
            vol.Required(
                CONF_BATTERY_COST_PER_KWH, default=current.get(CONF_BATTERY_COST_PER_KWH, DEFAULT_BATTERY_COST_PER_KWH)
            ): vol.All(vol.Coerce(float), vol.Range(min=100.0, max=2000.0)),
            vol.Required(
                CONF_BATTERY_LIFESPAN, default=current.get(CONF_BATTERY_LIFESPAN, DEFAULT_BATTERY_LIFESPAN)
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=30)),
            vol.Required(
                CONF_ENABLE_PEAK_SHAVING, default=current.get(CONF_ENABLE_PEAK_SHAVING, DEFAULT_ENABLE_PEAK_SHAVING)
            ): bool,
            vol.Required(
                CONF_PEAK_THRESHOLD_KW, default=current.get(CONF_PEAK_THRESHOLD_KW, DEFAULT_PEAK_THRESHOLD_KW)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=20.0)),
            vol.Required(
                CONF_SCAN_INTERVAL_HOURS, default=current.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
