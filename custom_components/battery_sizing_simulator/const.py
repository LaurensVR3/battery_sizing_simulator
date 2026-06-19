"""Constants for the Battery Sizing Simulator integration."""

DOMAIN = "battery_sizing_simulator"
PLATFORMS = ["sensor"]

# Config keys
CONF_GRID_EXPORT_SENSOR = "grid_export_sensor"
CONF_GRID_IMPORT_SENSOR = "grid_import_sensor"
CONF_CAPACITY_MIN = "capacity_min"
CONF_CAPACITY_MAX = "capacity_max"
CONF_CAPACITY_STEP = "capacity_step"
CONF_EFFICIENCY_CHARGE = "efficiency_charge"
CONF_EFFICIENCY_DISCHARGE = "efficiency_discharge"
CONF_MAX_DOD = "max_dod"
CONF_SELF_DISCHARGE_DAILY = "self_discharge_daily"
CONF_BATTERY_CHEMISTRY = "battery_chemistry"
CONF_INJECTION_TARIFF = "injection_tariff"
CONF_OFFTAKE_TARIFF_DAY = "offtake_tariff_day"
CONF_OFFTAKE_TARIFF_NIGHT = "offtake_tariff_night"
CONF_DAY_START_HOUR = "day_start_hour"
CONF_DAY_END_HOUR = "day_end_hour"
CONF_BATTERY_COST_PER_KWH = "battery_cost_per_kwh"
CONF_BATTERY_LIFESPAN = "battery_lifespan"
CONF_ANNUAL_DEGRADATION = "annual_degradation"
CONF_DISCOUNT_RATE = "discount_rate"
CONF_RESERVE_CAPACITY = "reserve_capacity"
CONF_ENABLE_PEAK_SHAVING = "enable_peak_shaving"
CONF_PEAK_THRESHOLD_KW = "peak_threshold_kw"
CONF_ELECTRICITY_PRICE_INFLATION = "electricity_price_inflation"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

# Battery chemistry presets
CHEMISTRY_LFP = "LFP"
CHEMISTRY_NMC = "NMC"
CHEMISTRY_CUSTOM = "Custom"

CHEMISTRY_PRESETS = {
    CHEMISTRY_LFP: {
        "max_dod": 0.90,
        "efficiency_charge": 0.97,
        "efficiency_discharge": 0.97,
        "self_discharge_daily": 0.0003,
        "annual_degradation": 0.02,
    },
    CHEMISTRY_NMC: {
        "max_dod": 0.80,
        "efficiency_charge": 0.96,
        "efficiency_discharge": 0.96,
        "self_discharge_daily": 0.0005,
        "annual_degradation": 0.025,
    },
}

# Default values
DEFAULT_CAPACITY_MIN = 2.0
DEFAULT_CAPACITY_MAX = 15.0
DEFAULT_CAPACITY_STEP = 1.0
DEFAULT_EFFICIENCY_CHARGE = 0.97
DEFAULT_EFFICIENCY_DISCHARGE = 0.97
DEFAULT_MAX_DOD = 0.90
DEFAULT_SELF_DISCHARGE_DAILY = 0.0003
DEFAULT_BATTERY_CHEMISTRY = CHEMISTRY_LFP
DEFAULT_INJECTION_TARIFF = 0.04       # €/kWh Belgium typical
DEFAULT_OFFTAKE_TARIFF_DAY = 0.28     # €/kWh Belgium typical day
DEFAULT_OFFTAKE_TARIFF_NIGHT = 0.22   # €/kWh Belgium typical night
DEFAULT_DAY_START_HOUR = 7
DEFAULT_DAY_END_HOUR = 22
DEFAULT_BATTERY_COST_PER_KWH = 600.0  # €/kWh installed
DEFAULT_BATTERY_LIFESPAN = 15
DEFAULT_ANNUAL_DEGRADATION = 0.02
DEFAULT_DISCOUNT_RATE = 0.03
DEFAULT_RESERVE_CAPACITY = 0.0
DEFAULT_ENABLE_PEAK_SHAVING = True
DEFAULT_PEAK_THRESHOLD_KW = 2.5       # Fluvius capaciteitstarief drempel
DEFAULT_ELECTRICITY_PRICE_INFLATION = 0.03
DEFAULT_SCAN_INTERVAL_HOURS = 24

# Sensor names
SENSOR_OPTIMAL_CAPACITY = "optimal_capacity"
SENSOR_OPTIMAL_PAYBACK = "optimal_payback_years"
SENSOR_OPTIMAL_NPV = "optimal_npv"
SENSOR_OPTIMAL_ANNUAL_SAVINGS = "optimal_annual_savings"
SENSOR_OPTIMAL_SELF_SUFFICIENCY = "optimal_self_sufficiency"
SENSOR_OPTIMAL_SELF_CONSUMPTION = "optimal_self_consumption"
SENSOR_SIMULATION_RESULTS = "simulation_results"
SENSOR_DATA_COVERAGE_DAYS = "data_coverage_days"
SENSOR_ANNUAL_EXPORT_KWH = "annual_export_kwh"
SENSOR_ANNUAL_IMPORT_KWH = "annual_import_kwh"
SENSOR_LAST_SIMULATION = "last_simulation"

# Statistics
STATISTICS_PERIOD = "hour"
MIN_DAYS_FOR_SIMULATION = 30  # Minimum days of data needed
IDEAL_DAYS_FOR_SIMULATION = 365

# Peak shaving (Fluvius capaciteitstarief)
PEAK_SHAVING_COST_PER_KW = 59.19  # €/kW/year (2024 Fluvius tarief)
QUARTER_HOURS_IN_MONTH = 4 * 24 * 30  # approximate
