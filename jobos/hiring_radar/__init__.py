"""Hiring Radar package."""

from __future__ import annotations

from jobos.hiring_radar.signals import SignalType, HiringSignal, process_signals
from jobos.hiring_radar.sources import scan_funding_rss, detect_velocity_spikes, parse_exec_departures

__all__ = [
    "SignalType",
    "HiringSignal",
    "process_signals",
    "scan_funding_rss",
    "detect_velocity_spikes",
    "parse_exec_departures",
]
