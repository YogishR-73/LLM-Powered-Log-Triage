"""Build candidate temporal relationships from canonical LogEvent records.

Events without timestamps are retained as nodes but do not participate in temporal
ordering. Edges represent candidate chronology, not proof of causality.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

import networkx as nx

_UNSET = object()


def _get(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _timestamp(event: Any, event_id: str) -> datetime | None:
    value = _get(event, "timestamp_iso")
    from_iso_field = value is not None
    if value is None:
        value = _get(event, "timestamp")
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(
                value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
            )
        except ValueError as exc:
            raise ValueError(f"Event {event_id!r} has invalid timestamp {value!r}") from exc
    if not isinstance(value, datetime):
        raise ValueError(f"Event {event_id!r} timestamp must be datetime, ISO string, or None")
    # Canonical timestamp_iso strings must carry an explicit UTC offset. Naive
    # datetimes remain supported only for legacy ``timestamp`` dictionaries.
    if from_iso_field and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"Event {event_id!r} timestamp_iso must include a UTC offset")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Event {event_id!r} has invalid timestamp timezone") from exc
    if value.tzinfo is not None and offset is None:
        raise ValueError(f"Event {event_id!r} has invalid timestamp timezone")
    return value


def _context(event: Any) -> dict[str, str]:
    attrs = _get(event, "attributes", {}) or {}
    result: dict[str, str] = {}
    for key in ("incident_id", "request_id", "trace_id", "correlation_id"):
        value = _get(event, key) or (attrs.get(key) if isinstance(attrs, Mapping) else None)
        if value is not None and str(value).strip():
            result[key] = str(value).strip()
    return result


class TemporalEventGraph:
    """Construct a time-windowed graph of candidate temporal relationships.

    Temporal edges point from an earlier event to a later event. By default,
    only consecutive timestamped records no more than 60 seconds apart are
    connected. ``max_gap_seconds=None`` explicitly disables the gap limit.
    """
    def __init__(self, max_gap_seconds: float | None = 60.0) -> None:
        self._validate_gap(max_gap_seconds)
        self.max_gap_seconds = max_gap_seconds
        self.graph = nx.DiGraph()

    @staticmethod
    def _validate_gap(value: float | None) -> None:
        if value is None:
            return
        error = "max_gap_seconds must be a finite non-negative number or None"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(error)
        try:
            normalized = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(error) from exc
        if not math.isfinite(normalized) or normalized < 0:
            raise ValueError(error)

    def build(self, events: Sequence[Any], *, max_gap_seconds: float | None | object = _UNSET) -> nx.DiGraph:
        # Omitted means use the constructor default; explicit None disables the gap limit.
        window = self.max_gap_seconds if max_gap_seconds is _UNSET else max_gap_seconds
        self._validate_gap(window)
        self.graph.clear()
        if not events:
            return self.graph

        rows: list[dict[str, Any]] = []
        explicit_ids: set[str] = set()
        for event in events:
            supplied_id = _get(event, "event_id")
            if supplied_id is not None:
                if not isinstance(supplied_id, str) or not supplied_id.strip():
                    raise ValueError("event_id must be a non-blank string")
                if supplied_id in explicit_ids:
                    raise ValueError(f"duplicate event_id: {supplied_id}")
                explicit_ids.add(supplied_id)

        generated_ids: set[str] = set()
        for index, event in enumerate(events):
            event_id = _get(event, "event_id")
            if event_id is None:
                if not isinstance(event, Mapping):
                    raise ValueError("LogEvent must provide event_id")
                event_id = f"E{index}"
                while event_id in explicit_ids or event_id in generated_ids:
                    event_id += "_generated"
                generated_ids.add(event_id)
            stamp = _timestamp(event, event_id)
            rows.append({
                "id": event_id, "event": event, "stamp": stamp,
                "index": index, "context": _context(event),
            })

        awareness = {
            r["stamp"].utcoffset() is not None
            for r in rows if r["stamp"] is not None
        }
        if len(awareness) > 1:
            raise ValueError("event timestamps must not mix timezone-aware and naive values")
        for row in rows:
            stamp = row["stamp"]
            if stamp is not None and stamp.utcoffset() is not None:
                row["stamp"] = stamp.astimezone(timezone.utc)

        for row in rows:
            event, stamp = row["event"], row["stamp"]
            self.graph.add_node(
                row["id"], timestamp=stamp, timestamp_iso=_get(event, "timestamp_iso"),
                temporal_unavailable=stamp is None,
                level=_get(event, "level", _get(event, "severity")),
                severity=_get(event, "severity", _get(event, "level")),
                service=_get(event, "service"), message=_get(event, "message"),
                source_file=_get(event, "source_file"), line_number=_get(event, "line_number"),
                template=_get(event, "template"), template_id=_get(event, "template_id"),
                event_id=row["id"], correlation_context=row["context"],
            )

        timed = sorted(
            (r for r in rows if r["stamp"] is not None),
            key=lambda r: (r["stamp"], r["index"]),
        )
        for current, following in zip(timed, timed[1:]):
            delta = (following["stamp"] - current["stamp"]).total_seconds()
            # Equal timestamps provide no precedence evidence.
            if delta <= 0:
                continue
            if not math.isfinite(delta):
                raise ValueError("timestamp difference must be finite")
            if window is not None and delta > window:
                continue
            a, b = current["context"], following["context"]
            shared_keys = set(a) & set(b)
            if any(a[k] != b[k] for k in shared_keys):
                continue
            shared = {k: a[k] for k in shared_keys}
            self.graph.add_edge(
                current["id"], following["id"],
                time_delta_seconds=delta,
                relationship="temporal_precedence",
                relationship_type="temporal_precedence",
                same_incident_window=True if shared else None,
                correlation_evidence=shared,
                temporal_order="before",
                candidate_relationship=True,
            )
        return self.graph

    def get_graph(self) -> nx.DiGraph:
        return self.graph
