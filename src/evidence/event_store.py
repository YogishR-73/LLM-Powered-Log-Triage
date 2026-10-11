"""Read-only event index for the evidence-grounding stage.

The store intentionally uses structural typing: it accepts Member 1's
``LogEvent`` without importing the upstream module at runtime. This avoids a
circular dependency and supports mapping records loaded from JSONL artifacts.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .schemas import EventSnapshot


class CanonicalLogEvent(Protocol):
    event_id: str
    timestamp_iso: str | None
    severity: str | None
    service: str | None
    message: str
    template: str | None
    source_file: str | None
    line_number: int | None


EventLike = CanonicalLogEvent | Mapping[str, Any]


class EventStore:
    """Index immutable event snapshots by their canonical event IDs.

    ``EventSnapshot`` deliberately retains only fields required for evidence
    references. Raw log payloads, parser internals, and arbitrary attributes
    are not copied into the evidence package.
    """

    __slots__ = ("_events",)

    def __init__(self, events: Iterable[EventLike]) -> None:
        snapshots: dict[str, EventSnapshot] = {}
        for event in events:
            snapshot = self._to_snapshot(event)
            if snapshot.event_id in snapshots:
                raise ValueError(f"Duplicate event_id: {snapshot.event_id}")
            snapshots[snapshot.event_id] = snapshot
        self._events = MappingProxyType(snapshots)

    @staticmethod
    def _read(event: EventLike, field: str) -> Any:
        if isinstance(event, Mapping):
            return event.get(field)
        return getattr(event, field, None)

    @classmethod
    def _to_snapshot(cls, event: EventLike) -> EventSnapshot:
        event_id = cls._read(event, "event_id")
        message = cls._read(event, "message")
        if not isinstance(event_id, str) or not event_id or not event_id.strip():
            raise ValueError("Every event must have a non-empty event_id")
        if event_id != event_id.strip():
            raise ValueError("event_id must not have leading or trailing whitespace")
        if not isinstance(message, str):
            raise ValueError(f"Event {event_id} must have a string message")

        line_number = cls._read(event, "line_number")
        # bool subclasses int in Python but is not a valid source line number.
        if line_number is not None and (
            isinstance(line_number, bool) or not isinstance(line_number, int)
        ):
            raise ValueError(f"Event {event_id} has a non-integer line_number")

        return EventSnapshot(
            event_id=event_id,
            timestamp_iso=cls._read(event, "timestamp_iso"),
            severity=cls._read(event, "severity"),
            service=cls._read(event, "service"),
            message=message,
            template=cls._read(event, "template"),
            source_file=cls._read(event, "source_file"),
            line_number=line_number,
        )

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "EventStore":
        """Load ``events.jsonl`` with file-and-line-aware validation errors.

        Each record is validated while its source line is known. Raw fields and
        unneeded parser metadata are discarded by ``_to_snapshot``.
        Blank lines and duplicate IDs are rejected explicitly so no records are
        silently lost.
        """
        source = Path(path)
        snapshots: dict[str, EventSnapshot] = {}
        with source.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ValueError(
                        f"Blank JSONL record at {source}:{line_number}"
                    )
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL record at {source}:{line_number}: {exc.msg}"
                    ) from exc

                if not isinstance(record, Mapping):
                    raise ValueError(
                        f"Invalid JSONL record at {source}:{line_number}: "
                        "expected a JSON object"
                    )

                try:
                    snapshot = cls._to_snapshot(record)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid event at {source}:{line_number}: {exc}"
                    ) from exc

                if snapshot.event_id in snapshots:
                    raise ValueError(
                        f"Duplicate event_id {snapshot.event_id!r} "
                        f"at {source}:{line_number}"
                    )
                snapshots[snapshot.event_id] = snapshot

        # The snapshots have already been validated; passing them through the
        # constructor maintains a single construction path for the read-only index.
        return cls(snapshots.values())

    def __len__(self) -> int:
        return len(self._events)

    def __contains__(self, event_id: object) -> bool:
        return isinstance(event_id, str) and event_id in self._events

    def get(self, event_id: str) -> EventSnapshot | None:
        if not isinstance(event_id, str):
            return None
        return self._events.get(event_id)

    def require(self, event_id: str) -> EventSnapshot:
        event = self.get(event_id)
        if event is None:
            raise KeyError(f"Unknown event_id: {event_id}")
        return event

    def ids(self) -> tuple[str, ...]:
        """Return event IDs in input/insertion order."""
        return tuple(self._events)
