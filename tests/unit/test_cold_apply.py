import pytest

from jobos.cold_apply.executor import ColdApplyExecutor
from jobos.cold_apply.field_mapper import map_fields

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


@pytest.mark.asyncio
async def test_submit_application_refuses_instead_of_claiming_success() -> None:
    """Browser automation is not implemented; it must never report success.

    The previous version returned {"status": "success"} with a screenshot path
    it never wrote, which would mark a job as applied-to when the candidate
    had not applied at all.
    """
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    with pytest.raises(NotImplementedError):
        await executor.submit_application("https://boards.example/job/1", dry_run=False)

    with pytest.raises(NotImplementedError):
        await executor.submit_application("https://boards.example/job/1", dry_run=True)


@pytest.mark.asyncio
async def test_fill_application_refuses_instead_of_claiming_filled() -> None:
    executor = ColdApplyExecutor(tenant_id="tenant-1")

    with pytest.raises(NotImplementedError):
        await executor.fill_application("https://boards.example/job/1", "/tmp/cv.pdf", {})


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
