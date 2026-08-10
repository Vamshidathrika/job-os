"""Tests for the ATS parse fidelity score.

The previous implementation returned a constant 1.0, so any threshold gating
on it passed unconditionally. These tests exist mainly to prove the score can
actually fail.
"""

import pytest

from jobos.tailorer.parse_tester import evaluate_parse_fidelity

ORIGINAL = """Asha Rao
asha@example.com
+91 98765 43210

Summary
Backend engineer focused on latency and reliability.

Experience
Acme — Backend Engineer
Built a Redis caching layer that cut P99 latency 45%.
Managed a team of 4 engineers.

Skills
Python, Postgres, Redis, Kubernetes

Education
IIT Madras
"""


def test_identical_resume_scores_perfectly():
    assert evaluate_parse_fidelity(ORIGINAL, ORIGINAL) == 1.0


def test_losing_the_email_is_penalised():
    """A resume without contact details is unreachable, whatever it says."""
    stripped = ORIGINAL.replace("asha@example.com", "")

    score = evaluate_parse_fidelity(ORIGINAL, stripped)

    assert score < 1.0


def test_losing_section_headings_is_penalised():
    flattened = ORIGINAL.replace("Experience", "").replace("Skills", "").replace("Education", "")

    assert evaluate_parse_fidelity(ORIGINAL, flattened) < 1.0


def test_wholesale_invention_scores_low():
    """Text with no grounding in the original must not score as faithful."""
    invented = """Jordan Smith
jordan@other.example

Experience
Globex — Principal Architect
Led 500 engineers across 12 countries.
"""

    assert evaluate_parse_fidelity(ORIGINAL, invented) < 0.5


def test_legitimate_trimming_still_scores_well():
    """Dropping irrelevant material is what tailoring is for — do not punish it."""
    trimmed = """Asha Rao
asha@example.com
+91 98765 43210

Summary
Backend engineer focused on latency and reliability.

Experience
Acme — Backend Engineer
Built a Redis caching layer that cut P99 latency 45%.

Skills
Python, Postgres, Redis

Education
IIT Madras
"""

    assert evaluate_parse_fidelity(ORIGINAL, trimmed) > 0.9


@pytest.mark.parametrize("original,tailored", [("", "text"), ("text", ""), ("", "")])
def test_empty_input_scores_zero(original: str, tailored: str):
    assert evaluate_parse_fidelity(original, tailored) == 0.0


def test_score_is_always_in_range():
    for tailored in (ORIGINAL, "", "unrelated text entirely", ORIGINAL * 3):
        score = evaluate_parse_fidelity(ORIGINAL, tailored)
        assert 0.0 <= score <= 1.0
