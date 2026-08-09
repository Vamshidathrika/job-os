"""Salary benchmark corpus module."""

from __future__ import annotations

import structlog
from typing import Any

logger = structlog.get_logger(__name__)


class SalaryCorpus:
    """Salary benchmark corpus for compensation intelligence."""

    def __init__(self) -> None:
        """Initialize the corpus with hardcoded Indian tech salary data."""
        self._data: dict[str, dict[str, Any]] = {}
        # Pre-load hardcoded salary data (in INR)
        self.add_data_point("Software Engineer", "India", 1500000.0, "internal_baseline")
        self.add_data_point("Senior Software Engineer", "India", 3000000.0, "internal_baseline")
        self.add_data_point("Staff Software Engineer", "India", 5000000.0, "internal_baseline")
        logger.info("initialized_salary_corpus", points_loaded=len(self._data))

    def lookup(self, title: str, location: str) -> dict[str, Any] | None:
        """
        Look up a salary band for a given title and location.
        """
        key = f"{title.lower().strip()}_{location.lower().strip()}"
        result = self._data.get(key)
        if result:
            logger.debug("corpus_lookup_hit", title=title, location=location)
        else:
            logger.debug("corpus_lookup_miss", title=title, location=location)
        return result

    def add_data_point(self, title: str, location: str, comp: float, source: str) -> None:
        """
        Add a salary data point to the corpus.
        """
        key = f"{title.lower().strip()}_{location.lower().strip()}"
        self._data[key] = {
            "p25": comp * 0.8,
            "p50": comp,
            "p75": comp * 1.2,
            "currency": "INR",
            "source": source,
        }
        logger.debug("added_corpus_data_point", title=title, location=location, source=source)
