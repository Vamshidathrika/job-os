"""Tests for the hiring radar's RSS funding detector."""

import pytest

from jobos.hiring_radar.signals import SignalType
from jobos.hiring_radar.sources import scan_funding_rss


def _feed(*items: tuple[str, str]) -> str:
    entries = "".join(
        f"<item><title>{title}</title><description>{desc}</description></item>"
        for title, desc in items
    )
    return f"<rss><channel>{entries}</channel></rss>"


@pytest.mark.asyncio
async def test_detects_funding_from_the_headline():
    signals = await scan_funding_rss(_feed(("Acme raises $20M Series B", "")))

    assert len(signals) == 1
    assert signals[0].signal_type is SignalType.FUNDING
    assert signals[0].company_name == "Acme"


@pytest.mark.asyncio
async def test_detects_funding_mentioned_only_in_the_body():
    """Funding feeds often keep the headline generic and put the round detail
    in the description, which the detector previously never read."""
    signals = await scan_funding_rss(
        _feed(("Acme announces its next chapter", "The company raised a $20M Series B."))
    )

    assert len(signals) == 1
    assert signals[0].company_name == "Acme"


@pytest.mark.asyncio
async def test_ignores_unrelated_items():
    signals = await scan_funding_rss(
        _feed(("Acme opens a Chennai office", "A new workspace for the team."))
    )

    assert signals == []


@pytest.mark.asyncio
async def test_malformed_feed_does_not_raise():
    assert await scan_funding_rss("<rss><channel><item>") == []


@pytest.mark.asyncio
async def test_url_input_is_not_parsed_as_xml():
    assert await scan_funding_rss("https://example.com/feed.xml") == []
