"""
Core battery simulation engine for the Battery Sizing Simulator.

Simulates a home battery for each capacity in a range using historical
grid export/import data. Calculates ROI, NPV, self-sufficiency, and
peak shaving benefits.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for the battery simulation."""
    # Battery physical parameters
    capacity_kwh: float          # Usable capacity to test
    efficiency_charge: float     # AC→DC charge efficiency (e.g. 0.97)
    efficiency_discharge: float  # DC→AC discharge efficiency (e.g. 0.97)
    max_dod: float               # Max depth of discharge (e.g. 0.90 for LFP)
    self_discharge_daily: float  # Daily self-discharge fraction (e.g. 0.0003)
    reserve_capacity: float      # Reserved SOC fraction (e.g. 0.20 for backup)

    # Financial parameters
    injection_tariff: float      # €/kWh paid for injection
    offtake_tariff_day: float    # €/kWh for daytime grid import
    offtake_tariff_night: float  # €/kWh for nighttime grid import
    day_start_hour: int          # Hour when day tariff starts (e.g. 7)
    day_end_hour: int            # Hour when day tariff ends (e.g. 22)
    battery_cost_per_kwh: float  # €/kWh installed cost
    battery_lifespan: int        # Years
    annual_degradation: float    # Annual capacity loss fraction
    discount_rate: float         # For NPV calculation
    electricity_price_inflation: float  # Annual electricity price increase

    # Peak shaving (Fluvius capaciteitstarief)
    enable_peak_shaving: bool = True
    peak_threshold_kw: float = 2.5
    peak_shaving_cost_per_kw: float = 59.19  # €/kW/year


@dataclass
class HourlyDataPoint:
    """One hour of grid data."""
    timestamp_hour: int   # Unix timestamp (start of hour)
    export_kwh: float     # Energy sent to grid this hour
    import_kwh: float     # Energy taken from grid this hour
    hour_of_day: int      # 0-23


@dataclass
class CapacityResult:
    """Simulation result for a single battery capacity."""
    capacity_kwh: float

    # Energy flows (annual)
    avoided_import_kwh: float = 0.0       # Grid import avoided by battery
    residual_export_kwh: float = 0.0      # Export that couldn't be stored
    stored_kwh: float = 0.0               # Total energy stored in battery
    discharged_kwh: float = 0.0           # Total energy discharged from battery
    losses_kwh: float = 0.0               # Total conversion + self-discharge losses

    # Self-sufficiency metrics
    self_sufficiency_pct: float = 0.0     # % of consumption covered without grid
    self_consumption_pct: float = 0.0     # % of own production consumed locally

    # Financial (annual)
    annual_savings_eur: float = 0.0       # Net annual savings vs no battery
    peak_shaving_savings_eur: float = 0.0 # Fluvius capaciteitstarief savings
    battery_annual_cost_eur: float = 0.0  # Annualised investment cost
    net_annual_benefit_eur: float = 0.0   # savings - cost

    # Financial (total)
    total_investment_eur: float = 0.0
    simple_payback_years: float = 0.0
    npv_eur: float = 0.0

    # Monthly breakdown for seasonal analysis
    monthly_avoided_import: list[float] = field(default_factory=lambda: [0.0] * 12)
    monthly_residual_export: list[float] = field(default_factory=lambda: [0.0] * 12)


def simulate_battery(
    data: list[HourlyDataPoint],
    config: SimulationConfig,
) -> CapacityResult:
    """
    Simulate a battery with the given capacity against historical data.

    The battery charges when there is surplus (grid export) and discharges
    when there is a deficit (grid import). Losses are accounted for on both
    sides. Self-discharge is applied once per simulated day.
    """
    result = CapacityResult(capacity_kwh=config.capacity_kwh)

    # Usable capacity accounting for reserve
    effective_capacity = config.capacity_kwh * config.max_dod * (1.0 - config.reserve_capacity)
    if effective_capacity <= 0:
        return result

    soc = 0.0  # State of charge in kWh (DC side)
    current_day = -1
    
    # Track peak power for Fluvius capaciteitstarief
    # We approximate: if import > threshold we could have avoided peak
    monthly_peak_reduction_kw: list[float] = [0.0] * 12

    total_import_kwh = sum(p.import_kwh for p in data)
    total_export_kwh = sum(p.export_kwh for p in data)

    for point in data:
        # Apply self-discharge once per simulated day
        day_index = point.timestamp_hour // 86400
        if day_index != current_day:
            soc *= (1.0 - config.self_discharge_daily)
            current_day = day_index

        # Determine tariff for this hour
        is_day_tariff = config.day_start_hour <= point.hour_of_day < config.day_end_hour
        tariff = config.offtake_tariff_day if is_day_tariff else config.offtake_tariff_night

        # Determine month for seasonal breakdown (0-indexed)
        month = _timestamp_to_month(point.timestamp_hour)

        # ── CHARGING ─────────────────────────────────────────────────────────
        if point.export_kwh > 0:
            # Max we can push into battery considering AC→DC efficiency and headroom
            headroom_dc = effective_capacity - soc
            # Energy we can charge (DC): limited by headroom
            # Energy input (AC) = charge_dc / efficiency
            # => charge_dc = min(export_ac * efficiency, headroom_dc)
            charge_dc = min(point.export_kwh * config.efficiency_charge, headroom_dc)
            charge_ac = charge_dc / config.efficiency_charge  # actual AC consumed

            soc += charge_dc
            result.stored_kwh += charge_dc
            result.residual_export_kwh += max(0, point.export_kwh - charge_ac)
            result.monthly_residual_export[month] += max(0, point.export_kwh - charge_ac)

        # ── DISCHARGING ──────────────────────────────────────────────────────
        if point.import_kwh > 0:
            # We want to deliver import_kwh to AC side
            # DC needed = import_kwh / discharge_efficiency, but limited by SOC
            discharge_dc = min(
                point.import_kwh / config.efficiency_discharge,
                soc
            )
            discharge_ac = discharge_dc * config.efficiency_discharge

            soc -= discharge_dc
            result.discharged_kwh += discharge_dc
            avoided = discharge_ac
            result.avoided_import_kwh += avoided
            result.monthly_avoided_import[month] += avoided

            # Peak shaving: track how much import we flattened below threshold
            if config.enable_peak_shaving and point.import_kwh > config.peak_threshold_kw:
                reduction = min(avoided, point.import_kwh - config.peak_threshold_kw)
                monthly_peak_reduction_kw[month] = max(
                    monthly_peak_reduction_kw[month], reduction
                )

    # ── RESIDUAL EXPORT: also add what we never stored ───────────────────────
    # Already tracked above. Now add to total.
    result.residual_export_kwh = sum(result.monthly_residual_export)

    # ── LOSSES ───────────────────────────────────────────────────────────────
    result.losses_kwh = result.stored_kwh - result.discharged_kwh

    # ── SELF-SUFFICIENCY & SELF-CONSUMPTION ──────────────────────────────────
    if total_import_kwh + result.avoided_import_kwh > 0:
        total_consumption = total_import_kwh + (total_export_kwh - result.residual_export_kwh)
        # Without battery, import was total_import_kwh
        # With battery, import is total_import_kwh - avoided_import_kwh
        result.self_sufficiency_pct = min(
            100.0,
            (result.avoided_import_kwh / total_import_kwh) * 100.0
            if total_import_kwh > 0 else 0.0
        )

    if total_export_kwh > 0:
        captured = total_export_kwh - result.residual_export_kwh
        result.self_consumption_pct = min(100.0, (captured / total_export_kwh) * 100.0)

    # ── FINANCIAL CALCULATIONS ────────────────────────────────────────────────
    # Scale data to full year if we have less
    days_of_data = len(set(p.timestamp_hour // 86400 for p in data))
    scale_factor = 365.0 / max(days_of_data, 1)

    annual_avoided_import = result.avoided_import_kwh * scale_factor
    annual_residual_export = result.residual_export_kwh * scale_factor
    # Without battery, all export was injected; with battery some is stored
    # Injection revenue we lose = (total_export - residual_export) * injection_tariff
    lost_injection = (total_export_kwh * scale_factor - annual_residual_export) * config.injection_tariff

    # Weighted average tariff for avoided import (rough 50/50 day/night split)
    avg_tariff = (config.offtake_tariff_day + config.offtake_tariff_night) / 2.0
    import_savings = annual_avoided_import * avg_tariff

    # Peak shaving savings (Fluvius: tariff is on highest monthly peak in kW)
    peak_shaving_annual = 0.0
    if config.enable_peak_shaving:
        for m in range(12):
            peak_shaving_annual += monthly_peak_reduction_kw[m] * (config.peak_shaving_cost_per_kw / 12.0)
    result.peak_shaving_savings_eur = peak_shaving_annual * scale_factor

    result.annual_savings_eur = import_savings - lost_injection + result.peak_shaving_savings_eur

    # Investment cost
    total_investment = config.capacity_kwh * config.battery_cost_per_kwh
    result.total_investment_eur = total_investment
    result.battery_annual_cost_eur = total_investment / config.battery_lifespan

    result.net_annual_benefit_eur = result.annual_savings_eur - result.battery_annual_cost_eur

    # Simple payback
    if result.annual_savings_eur > 0:
        result.simple_payback_years = total_investment / result.annual_savings_eur
    else:
        result.simple_payback_years = float("inf")

    # NPV over lifespan with degradation and electricity price inflation
    result.npv_eur = _calculate_npv(
        initial_investment=total_investment,
        annual_savings_year1=result.annual_savings_eur,
        battery_lifespan=config.battery_lifespan,
        annual_degradation=config.annual_degradation,
        electricity_price_inflation=config.electricity_price_inflation,
        discount_rate=config.discount_rate,
    )

    # Scale monthly arrays
    result.monthly_avoided_import = [v * scale_factor for v in result.monthly_avoided_import]
    result.monthly_residual_export = [v * scale_factor for v in result.monthly_residual_export]

    return result


def _calculate_npv(
    initial_investment: float,
    annual_savings_year1: float,
    battery_lifespan: int,
    annual_degradation: float,
    electricity_price_inflation: float,
    discount_rate: float,
) -> float:
    """
    Calculate Net Present Value of the battery investment.

    Each year:
    - Capacity degrades → savings drop proportionally
    - Electricity price inflates → savings increase proportionally
    - Both effects compound
    """
    npv = -initial_investment
    capacity_factor = 1.0
    price_factor = 1.0

    for year in range(1, battery_lifespan + 1):
        # Capacity degrades
        capacity_factor *= (1.0 - annual_degradation)
        # Price inflates
        price_factor *= (1.0 + electricity_price_inflation)

        year_savings = annual_savings_year1 * capacity_factor * price_factor
        discount = (1.0 + discount_rate) ** year
        npv += year_savings / discount

    return npv


def _timestamp_to_month(unix_timestamp: int) -> int:
    """Convert unix timestamp to 0-indexed month (0=Jan, 11=Dec)."""
    import time
    return time.gmtime(unix_timestamp).tm_mon - 1


def run_capacity_sweep(
    data: list[HourlyDataPoint],
    base_config: SimulationConfig,
    capacity_range: list[float],
) -> list[CapacityResult]:
    """
    Run simulation for each capacity in the range.
    Returns results sorted by capacity.
    """
    results = []
    for cap in capacity_range:
        cfg = SimulationConfig(
            capacity_kwh=cap,
            efficiency_charge=base_config.efficiency_charge,
            efficiency_discharge=base_config.efficiency_discharge,
            max_dod=base_config.max_dod,
            self_discharge_daily=base_config.self_discharge_daily,
            reserve_capacity=base_config.reserve_capacity,
            injection_tariff=base_config.injection_tariff,
            offtake_tariff_day=base_config.offtake_tariff_day,
            offtake_tariff_night=base_config.offtake_tariff_night,
            day_start_hour=base_config.day_start_hour,
            day_end_hour=base_config.day_end_hour,
            battery_cost_per_kwh=base_config.battery_cost_per_kwh,
            battery_lifespan=base_config.battery_lifespan,
            annual_degradation=base_config.annual_degradation,
            discount_rate=base_config.discount_rate,
            electricity_price_inflation=base_config.electricity_price_inflation,
            enable_peak_shaving=base_config.enable_peak_shaving,
            peak_threshold_kw=base_config.peak_threshold_kw,
            peak_shaving_cost_per_kw=base_config.peak_shaving_cost_per_kw,
        )
        result = simulate_battery(data, cfg)
        results.append(result)
        _LOGGER.debug(
            "Capacity %.1f kWh → NPV=€%.0f, payback=%.1fy, self-suff=%.1f%%",
            cap, result.npv_eur, result.simple_payback_years, result.self_sufficiency_pct
        )

    return sorted(results, key=lambda r: r.capacity_kwh)


def find_optimal_capacity(results: list[CapacityResult]) -> Optional[CapacityResult]:
    """
    Find optimal capacity by maximum NPV.
    Falls back to best payback if no positive NPV exists.
    """
    if not results:
        return None

    positive_npv = [r for r in results if r.npv_eur > 0]
    if positive_npv:
        return max(positive_npv, key=lambda r: r.npv_eur)

    # No positive NPV: return the one with best (lowest finite) payback
    finite_payback = [r for r in results if r.simple_payback_years < float("inf")]
    if finite_payback:
        return min(finite_payback, key=lambda r: r.simple_payback_years)

    return results[0]
