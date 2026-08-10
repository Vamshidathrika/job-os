"""Unit tests for Hiring Radar signal detection."""

import pytest
from jobos.hiring_radar import SignalType, scan_funding_rss


@pytest.mark.asyncio
async def test_scan_funding_rss() -> None:
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>TechCorp Raises $50M Series B</title>
                <description>TechCorp has just closed a $50M Series B funding round.</description>
                <link>http://example.com/techcorp</link>
            </item>
        </channel>
    </rss>
    """

    signals = await scan_funding_rss(rss_xml)
    assert len(signals) >= 1
    sig = signals[0]
    assert sig.signal_type == SignalType.FUNDING
    assert "TechCorp" in sig.company_name or "TechCorp" in sig.prediction
