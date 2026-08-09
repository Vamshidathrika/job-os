"""Referral Engine package."""

from __future__ import annotations

from jobos.referral.finder import find_referrers
from jobos.referral.scorer import score_referrer
from jobos.referral.sequence import generate_referral_sequence
from jobos.referral.suppression import check_suppression, add_to_suppression
from jobos.referral.network_mapper import map_existing_network

__all__ = [
    "find_referrers",
    "score_referrer",
    "generate_referral_sequence",
    "check_suppression",
    "add_to_suppression",
    "map_existing_network",
]
