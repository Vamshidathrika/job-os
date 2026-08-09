import pytest
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
