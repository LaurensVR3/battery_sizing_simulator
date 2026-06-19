"""
Fetches and processes Home Assistant recorder statistics for the
Battery Sizing Simulator.
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

HISTORY_DAYS = 365


async def fetch_hourly_data(
    hass: HomeAssistant,
    export_entity_id: str,
    import_entity_id: str,
    history_days: int = HISTORY_DAYS,
) -> tuple[list[HourlyDataPoint], int]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=history_days)

    statistic_ids = [export_entity_id, import_entity_id]

    try:
        stats = await get_instance(hass).async_add_executor_job(
            _fetch_stats, hass, start_time, end_time, statistic_ids,
        )
    except Exception as err:
        _LOGGER.error("Failed to fetch statistics: %s", err)
        return [], 0

    export_data = stats.get(export_entity_id, [])
    import_data = stats.get(import_entity_id, [])

    if not export_data and not import_data:
        _LOGGER.warning(
            "No statistics found for %s or %s.",
            export_entity_id, import_entity_id
        )
        return [], 0

    export_by_hour = _stats_to_hourly_dict(export_data)
    import_by_hour = _stats_to_hourly_dict(import_data)

    all_hours = sorted(set(export_by_hour.keys()) | set(import_by_hour.keys()))
    points: list[HourlyDataPoint] = []

    for ts in all_hours:
        points.append(HourlyDataPoint(
            timestamp_hour=ts,
            export_kwh=max(0.0, export_by_hour.get(ts, 0.0)),
            import_kwh=max(0.0, import_by_hour.get(ts, 0.0)),
            hour_of_day=datetime.fromtimestamp(ts, tz=timezone.utc).hour,
        ))

    days_covered = len(set(p.timestamp_hour // 86400 for p in points))
    _LOGGER.info(
        "Loaded %d hourly data points covering %d days (export: %.1f kWh, import: %.1f kWh)",
        len(points), days_covered,
        sum(p.export_kwh for p in points),
        sum(p.import_kwh for p in points),
    )

    return points, days_covered


def _fetch_stats(hass, start_time, end_time, statistic_ids):
    return statistics_during_period(
        hass=hass,
        start_time=start_time,
        end_time=end_time,
        statistic_ids=statistic_ids,
        period="hour",
        units={"energy": "kWh"},
        types={"sum", "change"},
    )


def _get(row, key):
    """Works for both dicts and objects."""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _start_to_ts(start_val) -> Optional[int]:
    if start_val is None:
        return None
    if isinstance(start_val, (int, float)):
        return int(start_val)
    if isinstance(start_val, datetime):
        return int(start_val.timestamp())
    try:
        return int(datetime.fromisoformat(str(start_val)).timestamp())
    except Exception:
        return None


def _stats_to_hourly_dict(stats: list) -> dict[int, float]:
    """
    statistics_during_period() geeft gewone dicts terug, geen objecten.
    Keys: 'start' (datetime), 'sum' (cumulatief), optioneel 'change' (delta).
    """
    result: dict[int, float] = {}

    if not stats:
        return result

    first = stats[0]
    has_change = _get(first, "change") is not None

    if has_change:
        for stat in stats:
            ts = _start_to_ts(_get(stat, "start"))
            change = _get(stat, "change")
            if ts is None or change is None:
                continue
            ts_hour = (ts // 3600) * 3600
            result[ts_hour] = result.get(ts_hour, 0.0) + float(change)
    else:
        prev_sum: Optional[float] = None
        for stat in stats:
            ts = _start_to_ts(_get(stat, "start"))
            sum_val = _get(stat, "sum")
            if ts is None or sum_val is None:
                continue
            ts_hour = (ts // 3600) * 3600
            current_sum = float(sum_val)
            if prev_sum is not None:
                result[ts_hour] = result.get(ts_hour, 0.0) + max(0.0, current_sum - prev_sum)
            prev_sum = current_sum

    return result


def get_data_summary(points: list[HourlyDataPoint]) -> dict:
    if not points:
        return {"status": "no_data"}

    days = len(set(p.timestamp_hour // 86400 for p in points))
    total_export = sum(p.export_kwh for p in points)
    total_import = sum(p.import_kwh for p in points)

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
