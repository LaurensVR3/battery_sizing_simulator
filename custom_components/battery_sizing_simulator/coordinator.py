"""
DataUpdateCoordinator for Battery Sizing Simulator.

Fetches data from HA statistics, runs the capacity sweep simulation,
and makes results available to sensor entities.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_GRID_EXPORT_SENSOR,
    CONF_GRID_IMPORT_SENSOR,
    CONF_CAPACITY_MIN,
    CONF_CAPACITY_MAX,
    CONF_CAPACITY_STEP,
    CONF_EFFICIENCY_CHARGE,
    CONF_EFFICIENCY_DISCHARGE,
    CONF_MAX_DOD,
    CONF_SELF_DISCHARGE_DAILY,
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
    MIN_DAYS_FOR_SIMULATION,
    PEAK_SHAVING_COST_PER_KW,
)
from .simulator import (
    SimulationConfig,
    CapacityResult,
    run_capacity_sweep,
    find_optimal_capacity,
    HourlyDataPoint,
)
from .statistics_helper import fetch_hourly_data, get_data_summary

_LOGGER = logging.getLogger(__name__)


class BatterySizingCoordinator(DataUpdateCoordinator):
    """Coordinator that runs the battery simulation periodically."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        cfg = entry.data

        scan_interval_hours = cfg.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval_hours),
        )

        self._results: list[CapacityResult] = []
        self._optimal: Optional[CapacityResult] = None
        self._data_summary: dict[str, Any] = {}
        self._days_covered: int = 0
        self._hourly_data: list[HourlyDataPoint] = []

    @property
    def results(self) -> list[CapacityResult]:
        """Return all capacity simulation results."""
        return self._results

    @property
    def optimal(self) -> Optional[CapacityResult]:
        """Return the optimal capacity result."""
        return self._optimal

    @property
    def data_summary(self) -> dict[str, Any]:
        """Return data availability summary."""
        return self._data_summary

    @property
    def days_covered(self) -> int:
        """Return number of days with data."""
        return self._days_covered

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and run simulation. Called by the coordinator."""
        cfg = self.entry.data

        export_entity = cfg[CONF_GRID_EXPORT_SENSOR]
        import_entity = cfg[CONF_GRID_IMPORT_SENSOR]

        # ── 1. Fetch historical data ──────────────────────────────────────────
        _LOGGER.info("Battery Sizing Simulator: fetching historical grid data...")
        points, days_covered = await fetch_hourly_data(
            self.hass,
            export_entity,
            import_entity,
        )

        self._days_covered = days_covered
        self._hourly_data = points
        self._data_summary = get_data_summary(points)

        if days_covered < MIN_DAYS_FOR_SIMULATION:
            msg = (
                f"Only {days_covered} days of data available. "
                f"Need at least {MIN_DAYS_FOR_SIMULATION} days for a meaningful simulation. "
                "Results will be available when more data is collected."
            )
            if days_covered == 0:
                raise UpdateFailed(
                    f"No statistics data found for {export_entity} or {import_entity}. "
                    "Check that these sensors have long-term statistics enabled."
                )
            _LOGGER.warning(msg)
            # Still run but warn about accuracy

        # ── 2. Build capacity range ───────────────────────────────────────────
        cap_min = cfg.get(CONF_CAPACITY_MIN, DEFAULT_CAPACITY_MIN)
        cap_max = cfg.get(CONF_CAPACITY_MAX, DEFAULT_CAPACITY_MAX)
        cap_step = cfg.get(CONF_CAPACITY_STEP, DEFAULT_CAPACITY_STEP)

        capacity_range = _build_capacity_range(cap_min, cap_max, cap_step)
        _LOGGER.debug("Simulating capacities: %s", capacity_range)

        # ── 3. Build base simulation config ──────────────────────────────────
        base_config = SimulationConfig(
            capacity_kwh=cap_min,  # will be overridden in sweep
            efficiency_charge=cfg.get(CONF_EFFICIENCY_CHARGE, DEFAULT_EFFICIENCY_CHARGE),
            efficiency_discharge=cfg.get(CONF_EFFICIENCY_DISCHARGE, DEFAULT_EFFICIENCY_DISCHARGE),
            max_dod=cfg.get(CONF_MAX_DOD, DEFAULT_MAX_DOD),
            self_discharge_daily=cfg.get(CONF_SELF_DISCHARGE_DAILY, DEFAULT_SELF_DISCHARGE_DAILY),
            reserve_capacity=cfg.get(CONF_RESERVE_CAPACITY, DEFAULT_RESERVE_CAPACITY),
            injection_tariff=cfg.get(CONF_INJECTION_TARIFF, DEFAULT_INJECTION_TARIFF),
            offtake_tariff_day=cfg.get(CONF_OFFTAKE_TARIFF_DAY, DEFAULT_OFFTAKE_TARIFF_DAY),
            offtake_tariff_night=cfg.get(CONF_OFFTAKE_TARIFF_NIGHT, DEFAULT_OFFTAKE_TARIFF_NIGHT),
            day_start_hour=cfg.get(CONF_DAY_START_HOUR, DEFAULT_DAY_START_HOUR),
            day_end_hour=cfg.get(CONF_DAY_END_HOUR, DEFAULT_DAY_END_HOUR),
            battery_cost_per_kwh=cfg.get(CONF_BATTERY_COST_PER_KWH, DEFAULT_BATTERY_COST_PER_KWH),
            battery_lifespan=cfg.get(CONF_BATTERY_LIFESPAN, DEFAULT_BATTERY_LIFESPAN),
            annual_degradation=cfg.get(CONF_ANNUAL_DEGRADATION, DEFAULT_ANNUAL_DEGRADATION),
            discount_rate=cfg.get(CONF_DISCOUNT_RATE, DEFAULT_DISCOUNT_RATE),
            electricity_price_inflation=cfg.get(
                CONF_ELECTRICITY_PRICE_INFLATION, DEFAULT_ELECTRICITY_PRICE_INFLATION
            ),
            enable_peak_shaving=cfg.get(CONF_ENABLE_PEAK_SHAVING, DEFAULT_ENABLE_PEAK_SHAVING),
            peak_threshold_kw=cfg.get(CONF_PEAK_THRESHOLD_KW, DEFAULT_PEAK_THRESHOLD_KW),
            peak_shaving_cost_per_kw=PEAK_SHAVING_COST_PER_KW,
        )

        # ── 4. Run capacity sweep in executor (CPU-bound) ─────────────────────
        _LOGGER.info(
            "Running battery simulation for %d capacities over %d data points (%d days)...",
            len(capacity_range), len(points), days_covered
        )

        results = await self.hass.async_add_executor_job(
            run_capacity_sweep,
            points,
            base_config,
            capacity_range,
        )

        self._results = results
        self._optimal = find_optimal_capacity(results)

        if self._optimal:
            _LOGGER.info(
                "Simulation complete. Optimal capacity: %.1f kWh | "
                "NPV: €%.0f | Payback: %.1f years | Self-sufficiency: %.1f%%",
                self._optimal.capacity_kwh,
                self._optimal.npv_eur,
                self._optimal.simple_payback_years,
                self._optimal.self_sufficiency_pct,
            )

        # ── 5. Return summary dict for coordinator.data ───────────────────────
        return {
            "days_covered": days_covered,
            "results_count": len(results),
            "optimal_capacity": self._optimal.capacity_kwh if self._optimal else None,
            "data_summary": self._data_summary,
        }


def _build_capacity_range(
    cap_min: float, cap_max: float, cap_step: float
) -> list[float]:
    """Build a list of capacity values to simulate."""
    if cap_step <= 0:
        cap_step = 1.0
    if cap_min >= cap_max:
        return [cap_min]

    result = []
    val = cap_min
    while val <= cap_max + 1e-9:
        result.append(round(val, 2))
        val += cap_step

    return result
