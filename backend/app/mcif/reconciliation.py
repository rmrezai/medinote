from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable


SOURCE_AUTHORITY = {
    "objective": 100,
    "consultant_documented": 90,
    "nursing_documented": 80,
    "clinician_documented": 70,
    "patient_reported": 45,
    "historical": 30,
    "derived": 25,
    "ai_interpretation": 10,
    None: 20,
}


@dataclass(frozen=True)
class TemporalItem:
    identifier: str
    concept: str
    value: str
    timestamp: datetime | None
    source_category: str | None = None


def authority(source_category: str | None) -> int:
    return SOURCE_AUTHORITY.get(source_category, 20)


def temporal_key(item: TemporalItem) -> tuple[int, datetime]:
    # Known timestamp beats unknown timestamp. Authority breaks equal-time ties.
    stamp = item.timestamp or datetime.min
    return (authority(item.source_category), stamp)


def choose_current(items: Iterable[TemporalItem]) -> TemporalItem | None:
    rows = list(items)
    if not rows:
        return None
    known = [x for x in rows if x.timestamp is not None]
    if known:
        newest_time = max(x.timestamp for x in known if x.timestamp is not None)
        same_time = [x for x in known if x.timestamp == newest_time]
        return max(same_time, key=lambda x: authority(x.source_category))
    return max(rows, key=lambda x: authority(x.source_category))


def numeric_trend(values: list[tuple[datetime | None, float]]) -> str:
    rows = [x for x in values if x[1] is not None]
    if len(rows) < 2:
        return "insufficient_data"
    rows.sort(key=lambda x: x[0] or datetime.min)
    first, last = rows[0][1], rows[-1][1]
    if first == last:
        return "stable"
    # Keep this descriptive, not diagnostic: rising/falling avoids assuming whether a change is clinically good or bad.
    return "rising" if last > first else "falling"


def oxygen_rank(device: str | None, flow: float | None, value_text: str | None = None) -> float:
    if device == "room_air" or value_text == "room_air":
        return 0.0
    if flow is not None:
        return float(flow)
    return 0.5


def oxygen_trend(rows: list[tuple[datetime | None, str | None, float | None, str | None]]) -> str:
    if len(rows) < 2:
        return "insufficient_data"
    rows.sort(key=lambda x: x[0] or datetime.min)
    first = oxygen_rank(rows[0][1], rows[0][2], rows[0][3])
    last = oxygen_rank(rows[-1][1], rows[-1][2], rows[-1][3])
    if first == last:
        return "stable"
    return "decreasing_support" if last < first else "increasing_support"


def normalize_value(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, Decimal):
        value = float(value)
    return str(value)
