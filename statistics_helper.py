"""
Fetches and processes Home Assistant recorder statistics for the
Battery Sizing Simulator.

Uses the internal HA statistics API to pull hourly kWh values for
grid export and import sensors over the past year (or available history).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    statistics_during_period,
)
from homeassistant.core import HomeAssistant

from .simulator import HourlyDataPoint

_LOGGER = logging.getLogger(__name__)

# How many days back to fetch (try for a full year)
HISTORY_DAYS = 365


async def fetch_hourly_data(
    hass: HomeAssistant,
    export_entity_id: str,
    import_entity_id: str,
    history_days: int = HISTORY_DAYS,
) -> tuple[list[HourlyDataPoint], int]:
    """
    Fetch hourly grid export and import data from HA recorder.

    Returns:
        - List of HourlyDataPoint sorted by timestamp
        - Number of actual days covered
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=history_days)

    statistic_ids = [
        _entity_to_statistic_id(export_entity_id),
        _entity_to_statistic_id(import_entity_id),
    ]

    _LOGGER.debug(
        "Fetching statistics for %s from %s to %s",
        statistic_ids, start_time.isoformat(), end_time.isoformat()
    )

    try:
        stats = await get_instance(hass).async_add_executor_job(
            _fetch_stats,
            hass,
            start_time,
            end_time,
            statistic_ids,
        )
    except Exception as err:
        _LOGGER.error("Failed to fetch statistics: %s", err)
        return [], 0

    export_stat_id = _entity_to_statistic_id(export_entity_id)
    import_stat_id = _entity_to_statistic_id(import_entity_id)

    export_data = stats.get(export_stat_id, [])
    import_data = stats.get(import_stat_id, [])

    if not export_data and not import_data:
        # Try with entity id directly (some integrations use entity_id as stat id)
        export_data = stats.get(export_entity_id, [])
        import_data = stats.get(import_entity_id, [])

    if not export_data and not import_data:
        _LOGGER.warning(
            "No statistics found for %s or %s. "
            "Make sure these sensors have long-term statistics enabled.",
            export_entity_id, import_entity_id
        )
        return [], 0

    # Convert to dict keyed by hour timestamp for alignment
    export_by_hour = _stats_to_hourly_dict(export_data)
    import_by_hour = _stats_to_hourly_dict(import_data)

    # Merge into HourlyDataPoint list
    all_hours = sorted(set(export_by_hour.keys()) | set(import_by_hour.keys()))
    points: list[HourlyDataPoint] = []

    for ts in all_hours:
        export_kwh = max(0.0, export_by_hour.get(ts, 0.0))
        import_kwh = max(0.0, import_by_hour.get(ts, 0.0))

        # hour_of_day from UTC timestamp
        hour_of_day = datetime.fromtimestamp(ts, tz=timezone.utc).hour

        points.append(HourlyDataPoint(
            timestamp_hour=ts,
            export_kwh=export_kwh,
            import_kwh=import_kwh,
            hour_of_day=hour_of_day,
        ))

    days_covered = len(set(p.timestamp_hour // 86400 for p in points))
    _LOGGER.info(
        "Loaded %d hourly data points covering %d days "
        "(export: %.1f kWh total, import: %.1f kWh total)",
        len(points),
        days_covered,
        sum(p.export_kwh for p in points),
        sum(p.import_kwh for p in points),
    )

    return points, days_covered


def _fetch_stats(
    hass: HomeAssistant,
    start_time: datetime,
    end_time: datetime,
    statistic_ids: list[str],
) -> dict:
    """Blocking call to fetch statistics (runs in executor)."""
    return statistics_during_period(
        hass=hass,
        start_time=start_time,
        end_time=end_time,
        statistic_ids=statistic_ids,
        period="hour",
        units={"energy": "kWh"},
        types={"sum", "change"},
    )


def _entity_to_statistic_id(entity_id: str) -> str:
    """
    HA statistics IDs are usually the entity_id for recorder-tracked sensors.
    Some external integrations use a custom statistic_id; we try the entity_id first.
    """
    return entity_id


def _stats_to_hourly_dict(stats: list) -> dict[int, float]:
    """
    Convert a list of StatisticData objects to a dict of {unix_hour: kwh}.

    HA statistics store cumulative sums. We use the 'change' field when
    available (hourly delta), otherwise we derive it from successive sum values.
    """
    result: dict[int, float] = {}

    if not stats:
        return result

    # Check if we have 'change' field (HA 2023.9+)
    first = stats[0]
    has_change = hasattr(first, "change") and first.change is not None

    if has_change:
        for stat in stats:
            if stat.start is None or stat.change is None:
                continue
            ts = int(stat.start.timestamp())
            # Round down to hour boundary
            ts_hour = (ts // 3600) * 3600
            result[ts_hour] = result.get(ts_hour, 0.0) + float(stat.change)
    else:
        # Derive hourly delta from cumulative sum
        prev_sum: Optional[float] = None
        for stat in stats:
            if stat.start is None or stat.sum is None:
                continue
            ts = int(stat.start.timestamp())
            ts_hour = (ts // 3600) * 3600
            current_sum = float(stat.sum)

            if prev_sum is not None:
                delta = max(0.0, current_sum - prev_sum)
                result[ts_hour] = result.get(ts_hour, 0.0) + delta

            prev_sum = current_sum

    return result


def get_data_summary(points: list[HourlyDataPoint]) -> dict:
    """Return a summary dict of the loaded data for diagnostics."""
    if not points:
        return {"status": "no_data"}

    days = len(set(p.timestamp_hour // 86400 for p in points))
    total_export = sum(p.export_kwh for p in points)
    total_import = sum(p.import_kwh for p in points)

    # Monthly breakdown
    monthly_export = [0.0] * 12
    monthly_import = [0.0] * 12
    for p in points:
        m = datetime.fromtimestamp(p.timestamp_hour, tz=timezone.utc).month - 1
        monthly_export[m] += p.export_kwh
        monthly_import[m] += p.import_kwh

    return {
        "status": "ok",
        "days_covered": days,
        "total_export_kwh": round(total_export, 1),
        "total_import_kwh": round(total_import, 1),
        "annual_export_kwh": round(total_export * 365 / max(days, 1), 1),
        "annual_import_kwh": round(total_import * 365 / max(days, 1), 1),
        "monthly_export_kwh": [round(v, 1) for v in monthly_export],
        "monthly_import_kwh": [round(v, 1) for v in monthly_import],
    }
