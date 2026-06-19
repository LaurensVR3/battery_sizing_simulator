"""
Sensor entities for Battery Sizing Simulator.

Creates a set of sensors in HA that expose:
- Optimal battery capacity
- NPV, payback period, annual savings
- Self-sufficiency and self-consumption rates
- Data coverage info
- Full simulation results (as JSON attribute) for Lovelace charting
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BatterySizingCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="optimal_capacity_kwh",
        name="Optimal Battery Capacity",
        native_unit_of_measurement="kWh",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_npv_eur",
        name="Optimal Battery NPV",
        native_unit_of_measurement="EUR",
        icon="mdi:cash-plus",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_payback_years",
        name="Optimal Battery Payback",
        native_unit_of_measurement="yr",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_annual_savings_eur",
        name="Optimal Battery Annual Savings",
        native_unit_of_measurement="EUR",
        icon="mdi:piggy-bank",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_net_annual_benefit_eur",
        name="Optimal Battery Net Annual Benefit",
        native_unit_of_measurement="EUR",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_self_sufficiency_pct",
        name="Self-Sufficiency with Optimal Battery",
        native_unit_of_measurement="%",
        icon="mdi:home-battery",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_self_consumption_pct",
        name="Self-Consumption with Optimal Battery",
        native_unit_of_measurement="%",
        icon="mdi:solar-power",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_avoided_import_kwh",
        name="Avoided Grid Import with Optimal Battery",
        native_unit_of_measurement="kWh",
        icon="mdi:transmission-tower-off",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_investment_eur",
        name="Optimal Battery Total Investment",
        native_unit_of_measurement="EUR",
        icon="mdi:currency-eur",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="optimal_peak_shaving_savings_eur",
        name="Peak Shaving Savings with Optimal Battery",
        native_unit_of_measurement="EUR",
        icon="mdi:chart-bell-curve",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="data_coverage_days",
        name="Simulation Data Coverage",
        native_unit_of_measurement="d",
        icon="mdi:database-clock",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="annual_export_kwh",
        name="Estimated Annual Grid Export",
        native_unit_of_measurement="kWh",
        icon="mdi:transmission-tower-export",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="annual_import_kwh",
        name="Estimated Annual Grid Import",
        native_unit_of_measurement="kWh",
        icon="mdi:transmission-tower-import",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="simulation_results_json",
        name="Battery Simulation Results",
        icon="mdi:chart-areaspline",
        # No unit/state_class: this is a JSON blob for charting
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for a config entry."""
    coordinator: BatterySizingCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BatterySizingsensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class BatterySizingensor(CoordinatorEntity[BatterySizingCoordinator], SensorEntity):
    """A single sensor entity for the Battery Sizing Simulator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatterySizingCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Battery Sizing Simulator",
            manufacturer="Custom Integration",
            model="Battery ROI Calculator",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        key = self.entity_description.key
        coordinator = self.coordinator
        optimal = coordinator.optimal
        summary = coordinator.data_summary

        # ── Data availability sensors ─────────────────────────────────────────
        if key == "data_coverage_days":
            return coordinator.days_covered

        if key == "annual_export_kwh":
            return summary.get("annual_export_kwh")

        if key == "annual_import_kwh":
            return summary.get("annual_import_kwh")

        # ── Optimal capacity sensors ──────────────────────────────────────────
        if optimal is None:
            return None

        if key == "optimal_capacity_kwh":
            return round(optimal.capacity_kwh, 1)

        if key == "optimal_npv_eur":
            return round(optimal.npv_eur, 0)

        if key == "optimal_payback_years":
            if optimal.simple_payback_years == float("inf"):
                return None
            return round(optimal.simple_payback_years, 1)

        if key == "optimal_annual_savings_eur":
            return round(optimal.annual_savings_eur, 0)

        if key == "optimal_net_annual_benefit_eur":
            return round(optimal.net_annual_benefit_eur, 0)

        if key == "optimal_self_sufficiency_pct":
            return round(optimal.self_sufficiency_pct, 1)

        if key == "optimal_self_consumption_pct":
            return round(optimal.self_consumption_pct, 1)

        if key == "optimal_avoided_import_kwh":
            return round(optimal.avoided_import_kwh, 1)

        if key == "optimal_investment_eur":
            return round(optimal.total_investment_eur, 0)

        if key == "optimal_peak_shaving_savings_eur":
            return round(optimal.peak_shaving_savings_eur, 0)

        # ── Full results JSON (for Lovelace charting) ─────────────────────────
        if key == "simulation_results_json":
            return self._build_results_json()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes with full simulation data."""
        key = self.entity_description.key
        optimal = self.coordinator.optimal
        summary = self.coordinator.data_summary

        if key == "optimal_capacity_kwh" and optimal:
            return {
                "capacity_kwh": optimal.capacity_kwh,
                "npv_eur": round(optimal.npv_eur, 0),
                "payback_years": round(optimal.simple_payback_years, 1)
                    if optimal.simple_payback_years != float("inf") else None,
                "annual_savings_eur": round(optimal.annual_savings_eur, 0),
                "battery_annual_cost_eur": round(optimal.battery_annual_cost_eur, 0),
                "net_annual_benefit_eur": round(optimal.net_annual_benefit_eur, 0),
                "self_sufficiency_pct": round(optimal.self_sufficiency_pct, 1),
                "self_consumption_pct": round(optimal.self_consumption_pct, 1),
                "avoided_import_kwh": round(optimal.avoided_import_kwh, 1),
                "residual_export_kwh": round(optimal.residual_export_kwh, 1),
                "losses_kwh": round(optimal.losses_kwh, 1),
                "peak_shaving_savings_eur": round(optimal.peak_shaving_savings_eur, 0),
                "total_investment_eur": round(optimal.total_investment_eur, 0),
                "monthly_avoided_import_kwh": [round(v, 1) for v in optimal.monthly_avoided_import],
                "monthly_residual_export_kwh": [round(v, 1) for v in optimal.monthly_residual_export],
            }

        if key == "data_coverage_days":
            return {
                "total_export_kwh": summary.get("total_export_kwh"),
                "total_import_kwh": summary.get("total_import_kwh"),
                "monthly_export_kwh": summary.get("monthly_export_kwh", []),
                "monthly_import_kwh": summary.get("monthly_import_kwh", []),
            }

        return {}

    def _build_results_json(self) -> str:
        """Build a compact JSON string of all capacity results for charting."""
        results = self.coordinator.results
        if not results:
            return json.dumps({"capacities": [], "npv": [], "payback": [], "savings": []})

        data = {
            "capacities": [r.capacity_kwh for r in results],
            "npv_eur": [round(r.npv_eur, 0) for r in results],
            "payback_years": [
                round(r.simple_payback_years, 1) if r.simple_payback_years != float("inf") else None
                for r in results
            ],
            "annual_savings_eur": [round(r.annual_savings_eur, 0) for r in results],
            "net_annual_benefit_eur": [round(r.net_annual_benefit_eur, 0) for r in results],
            "self_sufficiency_pct": [round(r.self_sufficiency_pct, 1) for r in results],
            "self_consumption_pct": [round(r.self_consumption_pct, 1) for r in results],
            "avoided_import_kwh": [round(r.avoided_import_kwh, 1) for r in results],
            "investment_eur": [round(r.total_investment_eur, 0) for r in results],
        }
        return json.dumps(data)
