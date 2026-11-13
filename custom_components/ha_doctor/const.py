"""HA Doctor scan settings."""

from datetime import timedelta

DOMAIN = "ha_doctor"
NAME = "HA Doctor"
SCAN_INTERVAL = timedelta(minutes=1)
OUTAGE_THRESHOLD = timedelta(minutes=15)
