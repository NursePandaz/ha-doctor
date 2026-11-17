"""Check the exact outage boundary using Home Assistant State objects."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import State

from custom_components.ha_doctor.scanner import is_persistent_outage


@pytest.mark.parametrize(
    ("value", "age_seconds", "attributes", "expected"),
    [
        ("unavailable", 899, {}, False),
        ("unavailable", 900, {}, True),
        ("unavailable", 3600, {}, True),
        ("unknown", 3600, {}, False),
        ("on", 3600, {}, False),
        ("unavailable", 3600, {"restored": True}, False),
    ],
)
def test_persistent_outage(value, age_seconds, attributes, expected):
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    state = State(
        "sensor.room",
        value,
        attributes,
        last_changed=now - timedelta(seconds=age_seconds),
    )
    assert is_persistent_outage(state, now, timedelta(minutes=15)) is expected
