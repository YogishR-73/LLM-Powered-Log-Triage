"""Real Member 1 schema contract test.

Skipped only when src.log_intelligence is not in the checkout yet. If the module
exists but has a broken import, the test should fail rather than masking it.
"""
from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("src.log_intelligence") is None:
    pytest.skip("Member 1's src.log_intelligence is not present in this checkout", allow_module_level=True)

# Intentionally not wrapped in try/except: broken internal imports should fail CI.
from src.log_intelligence import LogEvent
from src.evidence import EventStore


def test_event_store_accepts_real_member1_logevent():
    event = LogEvent(
        event_id="evt_0123456789abcdef",
        timestamp_iso="2026-10-08T10:00:00+00:00",
        severity="ERROR",
        service="checkout",
        message="checkout request timed out",
        template="checkout request timed out",
        template_id="tpl_0123456789ab",
        source_file="checkout.log",
        line_number=17,
        raw="2026-10-08T10:00:00Z ERROR checkout request timed out",
        parser="generic_iso",
    )
    store = EventStore([event])
    snapshot = store.require(event.event_id)
    assert snapshot.event_id == event.event_id
    assert snapshot.timestamp_iso == event.timestamp_iso
    assert snapshot.service == "checkout"
    assert snapshot.message == event.message
    assert snapshot.line_number == 17
    assert not hasattr(snapshot, "raw")
