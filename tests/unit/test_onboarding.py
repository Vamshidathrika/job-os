import json

import pytest
from jobos.onboarding.wizard import OnboardingWizard
from jobos.onboarding.shadow_mode import ShadowMode
from jobos.onboarding.resume_parser import parse_uploaded_resume

@pytest.mark.asyncio
async def test_onboarding_wizard_start() -> None:
    """Test wizard returns all required steps."""
    wizard = OnboardingWizard(tenant_id="tenant_123")
    progress = await wizard.start()
    
    assert "completed_steps" in progress
    assert "pending_steps" in progress
    assert len(progress["pending_steps"]) > 0
    assert progress["percent_complete"] == 0.0
    
    expected_steps = [
        "resume_upload",
        "target_roles",
        "target_companies",
        "location_preferences",
        "salary_expectations",
        "integration_setup",
    ]
    for step in expected_steps:
        assert step in progress["pending_steps"]

# Shadow mode is now backed by tenants.autonomy_mode and the action_queue,
# so it is exercised for real in tests/integration/test_shadow_mode.py.

@pytest.mark.asyncio
async def test_parse_uploaded_resume(tmp_path, mocker) -> None:
    """Test resume parsing returns structured data from the real file."""
    resume = tmp_path / "resume.txt"
    resume.write_text("Asha Rao\nasha@example.com\nEngineer at Freshworks\n")

    mocker.patch(
        "jobos.onboarding.resume_parser.acompletion",
        return_value={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "name": "Asha Rao",
                                "email": "asha@example.com",
                                "experience": [{"company": "Freshworks", "title": "Engineer"}],
                                "skills": ["python"],
                            }
                        )
                    }
                }
            ]
        },
    )

    result = await parse_uploaded_resume(str(resume))

    assert "name" in result
    assert "email" in result
    assert "experience" in result
    assert "skills" in result
    assert result["name"] == "Asha Rao"


@pytest.mark.asyncio
async def test_parse_uploaded_resume_missing_file_raises() -> None:
    """A missing upload must fail loudly, not return a fabricated profile."""
    with pytest.raises(FileNotFoundError):
        await parse_uploaded_resume("/tmp/does_not_exist_resume.pdf")
