"""Defaults for existing entries and first-time setup."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

DOMAIN = "ha_doctor"
NAME = "HA Doctor"


@dataclass(frozen=True)
class Settings:
    """Scan and presentation preferences stored in the config entry."""

    interval: int = 1
    threshold: int = 15
    excluded: frozenset[str] = frozenset()
    individual: bool = False

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> "Settings":
        return cls(
            interval=options.get("interval", cls.interval),
            threshold=options.get("threshold", cls.threshold),
            excluded=frozenset(options.get("excluded", ())),
            individual=options.get("individual", cls.individual),
        )

    @property
    def outage_duration(self) -> timedelta:
        return timedelta(minutes=self.threshold)
