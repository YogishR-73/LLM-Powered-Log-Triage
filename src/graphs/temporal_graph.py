"""Build candidate temporal relationships from canonical LogEvent records.

Events without timestamps are retained as nodes but do not participate in temporal
ordering. Edges represent candidate chronology, not proof of causality.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

import networkx as nx


def _get(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _timestamp(event: Any, event_id: str) -> datetime | None:
    value = _get(event, "timestamp_iso")
    if value is None:
        value = _get(event, "timestamp")
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Event {event_id!r} has invalid timestamp {value!r}") from exc
    if not isinstance(value, datetime):
        raise ValueError(f"Event {event_id!r} timestamp must be datetime, ISO string, or None")
    # Canonical LogEvent requires offsets. Legacy dictionaries may be naive; these
    # are accepted only when all present timestamps are naive.
    return value


def _context(event: Any) -> dict[str, str]:
    attrs = _get(event, "attributes", {}) or {}
    result = {}
    for key in ("incident_id", "request_id", "trace_id", "correlation_id"):
        value = _get(event, key) or (attrs.get(key) if isinstance(attrs, Mapping) else None)
        if value is not None and str(value).strip():
            result[key] = str(value).strip()
    return result


class TemporalEventGraph:
    """Construct a time-windowed graph of candidate temporal relationships.

    ``consumer -> provider`` is a service-graph convention; this graph instead
    points from an earlier event to a later event. Correlation metadata is kept
    explicit so consumers can distinguish confirmed shared context from unknown.
    """

    def __init__(self, max_gap_seconds: float | None = 60.0) -> None:
        self._validate_gap(max_gap_seconds)
        self.max_gap_seconds = max_gap_seconds
        self.graph = nx.DiGraph()

    @staticmethod
    def _validate_gap(value: float | None) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0
        ):
            raise ValueError("max_gap_seconds must be a finite non-negative number or None")

    def build(self, events: Sequence[Any], *, max_gap_seconds: float | None = None) -> nx.DiGraph:
        window = self.max_gap_seconds if max_gap_seconds is None else max_gap_seconds
        self._validate_gap(window)
        self.graph.clear()
        if not events:
            return self.graph

        rows = []
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
            # Canonical LogEvent IDs are mandatory. Fallback IDs exist only for
            # legacy dict inputs, and are namespaced to avoid collisions.
            if event_id is None:
                if not isinstance(event, Mapping):
                    raise ValueError("LogEvent must provide event_id")
                event_id = f"E{index}"
                while event_id in explicit_ids or event_id in generated_ids:
                    event_id += "_generated"
                generated_ids.add(event_id)
            stamp = _timestamp(event, event_id)
            rows.append({"id": event_id, "event": event, "stamp": stamp,
                         "index": index, "context": _context(event)})

        # Check timezone consistency among timestamped records; then normalize aware
        # timestamps to UTC for stable ordering across different offsets.
        awareness = {r["stamp"].utcoffset() is not None for r in rows if r["stamp"] is not None}
        if len(awareness) > 1:
            raise ValueError("event timestamps must not mix timezone-aware and naive values")
        for row in rows:
            stamp = row["stamp"]
            if stamp is not None and stamp.utcoffset() is not None:
                row["stamp"] = stamp.astimezone(timezone.utc)

        for row in rows:
            event = row["event"]
            stamp = row["stamp"]
            self.graph.add_node(
                row["id"], timestamp=stamp,
                temporal_unavailable=stamp is None,
                level=_get(event, "level"), severity=_get(event, "severity", _get(event, "level")),
                service=_get(event, "service"), message=_get(event, "message"),
                source_file=_get(event, "source_file"), line_number=_get(event, "line_number"),
                template=_get(event, "template"), template_id=_get(event, "template_id"),
                event_id=row["id"], correlation_context=row["context"],
            )

        timed = sorted((r for r in rows if r["stamp"] is not None), key=lambda r: (r["stamp"], r["index"]))
        for current, following in zip(timed, timed[1:]):
            delta = (following["stamp"] - current["stamp"]).total_seconds()
            if delta <= 0:  # equal timestamps do not establish precedence
                continue
            if window is not None and delta > window:
                continue
            a, b = current["context"], following["context"]
            shared_keys = set(a) & set(b)
            conflicts = any(a[k] != b[k] for k in shared_keys)
            if conflicts:
                continue
            shared = {k: a[k] for k in shared_keys}
            same_incident = True if shared else None  # None means not established
            self.graph.add_edge(
                current["id"], following["id"],
                time_delta_seconds=delta,
                relationship="temporal_precedence",
                relationship_type="temporal_precedence",
                same_incident_window=same_incident,
                correlation_evidence=shared,
                temporal_order="before",
                candidate_relationship=True,
            )
        return self.graph

    def get_graph(self) -> nx.DiGraph:
        return self.graph
