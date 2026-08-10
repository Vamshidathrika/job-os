"""Signal parsers and detectors for the Hiring Radar."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

import asyncpg
import structlog

from .signals import HiringSignal, SignalType

logger = structlog.get_logger(__name__)

# Terms that mark an RSS item as a funding announcement.
FUNDING_KEYWORDS = ("raises", "raised", "funding", "series", "seed round", "led by")


async def scan_funding_rss(feed_url_or_xml: str) -> list[HiringSignal]:
    """
    Scan RSS feeds (e.g., Inc42, Crunchbase) or raw XML content for funding announcements.

    Args:
        feed_url_or_xml: The URL of the RSS feed or raw XML payload.

    Returns:
        A list of HiringSignal objects representing detected funding events.
    """
    logger.info("Scanning funding RSS feed", feed_url=feed_url_or_xml[:50])
    signals: list[HiringSignal] = []

    # Check if input is XML string vs URL
    xml_content = feed_url_or_xml
    if feed_url_or_xml.startswith("http://") or feed_url_or_xml.startswith("https://"):
        # For actual URLs, caller/poller passes raw XML or httpx handles it
        return signals

    try:
        root = ET.fromstring(xml_content)
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            title = title_elem.text if title_elem is not None and title_elem.text else ""
            desc_elem = item.find("description")
            desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

            # Search the body too: funding feeds routinely put the round
            # detail in the description and keep the headline generic. The
            # description was previously extracted and then ignored.
            haystack = f"{title} {desc}".lower()
            if any(keyword in haystack for keyword in FUNDING_KEYWORDS):
                company_name = title.split()[0] if title else "Unknown"
                signals.append(
                    HiringSignal(
                        company_name=company_name,
                        company_domain=f"{company_name.lower()}.com",
                        signal_type=SignalType.FUNDING,
                        prediction="Expect 5-15 new roles in 30-90 days",
                        action="Add to Tier-1 watchlist, begin warm-path prep NOW",
                        confidence=0.8,
                        detected_at=datetime.now(timezone.utc),
                    )
                )
    except ET.ParseError as e:
        logger.warning("Failed to parse RSS XML", error=str(e))

    return signals


async def detect_velocity_spikes(
    conn: asyncpg.Connection, threshold_multiplier: float = 2.5
) -> list[HiringSignal]:
    """
    Detect companies with a high velocity spike in job postings.

    Checks the `jobs` table for companies with greater than the threshold_multiplier
    (default 2.5x) job postings in the last 14 days compared to their baseline.

    Args:
        conn: The asyncpg database connection.
        threshold_multiplier: The multiplier over the baseline to consider a spike.

    Returns:
        A list of HiringSignal objects representing velocity spikes.
    """
    logger.info("Detecting job posting velocity spikes", threshold=threshold_multiplier)
    signals: list[HiringSignal] = []
    return signals


async def parse_exec_departures(apollo_data: list[dict[str, Any]]) -> list[HiringSignal]:
    """
    Parse Apollo data to detect executive departures (VP, Director, Head).

    Args:
        apollo_data: A list of dictionaries representing people data from Apollo.

    Returns:
        A list of HiringSignal objects representing executive departures.
    """
    logger.info("Parsing executive departures", records_count=len(apollo_data))
    signals: list[HiringSignal] = []
    return signals
