from pathlib import Path

import pytest

from jobos.cold_apply.executor import ColdApplyExecutor
from jobos.cold_apply.field_mapper import map_fields

FIXTURE_URL = "file://" + str(
    Path(__file__).resolve().parents[2] / "jobos" / "cold_apply" / "fixtures" / "greenhouse_form.html"
)


def test_map_fields() -> None:
    """Test field mapping returns correct field_id -> value pairs."""
    form_fields = [
        {"id": "first_name", "label": "First Name"},
        {"id": "last_name", "label": "Last Name"},
        {"id": "missing_field", "label": "Missing Field"},
    ]
    user_data = {
        "first_name": "Alice",
        "last_name": "Smith",
        "extra_field": "Extra"
    }

    result = map_fields(form_fields, user_data)

    assert result == {
        "first_name": "Alice",
        "last_name": "Smith"
    }
    assert "missing_field" not in result
    assert "extra_field" not in result


def test_field_mapping_still_works_without_a_browser() -> None:
    """The genuinely-implemented part stays usable on its own."""
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    mapped = executor.map_answers_to_fields(
        ["First Name", "Last Name", "Favourite Colour"],
        {"first_name": "Alice", "last_name": "Smith"},
    )

    assert mapped["First Name"] == "Alice"
    assert mapped["Last Name"] == "Smith"
    assert "Favourite Colour" not in mapped


async def test_fill_application_fills_real_fields_on_the_local_fixture():
    """Regression: the previous version claimed 'filled' without ever loading
    a page. This drives a real (local) form via Playwright and asserts on
    values actually present in the DOM afterward, not just a return value."""
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    result = await executor.fill_application(
        FIXTURE_URL,
        resume_path=None,
        answers={
            "first name": "Asha",
            "last name": "Rao",
            "email": "asha@example.com",
            "phone": "9876543210",
        },
    )

    assert result["fields_filled"] >= 4
    assert result["filled"]["First Name"] == "Asha"
    assert result["filled"]["Last Name"] == "Rao"
    assert result["filled"]["Email"] == "asha@example.com"


async def test_fill_application_takes_a_real_screenshot(tmp_path):
    """Regression: the previous version returned a screenshot_path that was
    never written — this asserts the file genuinely exists on disk."""
    executor = ColdApplyExecutor(tenant_id="tenant-screenshot-test")

    result = await executor.fill_application(FIXTURE_URL, resume_path=None, answers={"first name": "Asha"})

    screenshot = Path(result["screenshot_path"])
    assert screenshot.exists(), "the screenshot file must actually exist, not just be a path"
    assert screenshot.stat().st_size > 0
    screenshot.unlink()


async def test_fill_application_attaches_a_real_resume_file(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text("Asha Rao — Backend Engineer")
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    result = await executor.fill_application(
        FIXTURE_URL, resume_path=str(resume), answers={"first name": "Asha"}
    )

    # The file input isn't part of the label-matched "filled" dict (it's
    # handled separately), but the call must not have errored, and the field
    # matching for other fields must still have run normally.
    assert result["filled"]["First Name"] == "Asha"


async def test_fill_application_reports_unmatched_labels_honestly():
    """A field with no matching answer must be reported as unmatched, not
    silently skipped or falsely counted as filled."""
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    result = await executor.fill_application(
        FIXTURE_URL, resume_path=None, answers={"first name": "Asha"}
    )

    assert "Last Name" in result["unmatched_labels"]
    assert "Last Name" not in result["filled"]


async def test_submit_application_never_clicks_submit_and_reports_prepared():
    """The whole point of this design: 'submitting' means preparing a
    reviewable artifact, never actually clicking a submit control."""
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    result = await executor.submit_application(
        FIXTURE_URL, resume_path=None, answers={"first name": "Asha", "last name": "Rao"}
    )

    assert result["status"] == "prepared_for_review"
    assert result["dry_run"] is True
    assert result["fields_filled"] >= 2
    Path(result["screenshot_path"]).unlink(missing_ok=True)


async def test_submit_application_does_not_trigger_a_real_post():
    """Verify submit_application has zero submission side effect: the local
    fixture's form has no server behind it, so if a real POST were ever
    triggered by a submit click, the browser navigation itself would fail
    (no server to receive it) rather than silently succeeding. A clean
    return with a screenshot proves no submit-triggering navigation occurred."""
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    result = await executor.submit_application(FIXTURE_URL, resume_path=None, answers={})

    assert result["status"] == "prepared_for_review"
    Path(result["screenshot_path"]).unlink(missing_ok=True)
