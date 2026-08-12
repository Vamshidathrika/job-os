"""Unit tests for the Composio-backed Google Drive integration.

A fake ComposioClient stands in for the SDK — there is no API key in CI —
but the request shaping, idempotent folder handling, and failure propagation
under test are the real implementation.
"""

import pytest

from jobos.composio_client import ComposioActionError
from jobos.integrations.drive import DriveClient


class FakeComposio:
    """Records executed actions and replays canned responses."""

    def __init__(self, responses=None, error: Exception | None = None):
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, action: str, params: dict) -> dict:
        self.calls.append((action, params))
        if self.error:
            raise self.error
        return self.responses.get(action, {})


async def test_upload_resume_returns_the_real_file_id():
    fake = FakeComposio(
        {"GOOGLEDRIVE_CREATE_FILE_FROM_TEXT": {"id": "1AbCdEfGh", "webViewLink": "https://drive.google.com/file/d/1AbCdEfGh/view"}}
    )
    client = DriveClient(tenant_id="t1", composio=fake)

    result = await client.upload_resume(
        tenant_id="t1", filename="resume-postman.txt", text_content="Cut p99 latency 45%..."
    )

    action, params = fake.calls[-1]
    assert action == "GOOGLEDRIVE_CREATE_FILE_FROM_TEXT"
    assert params["name"] == "resume-postman.txt"
    assert "Cut p99 latency" in params["text_content"]

    assert result["file_id"] == "1AbCdEfGh"
    assert result["file_id"] != "mock_file_id"
    assert result["web_view_link"] == "https://drive.google.com/file/d/1AbCdEfGh/view"


async def test_upload_resume_propagates_failure_instead_of_faking_success():
    fake = FakeComposio(error=ComposioActionError("drive quota exceeded"))
    client = DriveClient(tenant_id="t1", composio=fake)

    with pytest.raises(ComposioActionError):
        await client.upload_resume(tenant_id="t1", filename="resume.txt", text_content="body")


async def test_ensure_folder_reuses_an_existing_folder():
    fake = FakeComposio({"GOOGLEDRIVE_FIND_FILE": {"files": [{"id": "folder-existing"}]}})
    client = DriveClient(tenant_id="t1", composio=fake)

    result = await client.ensure_folder("JOBOS Resumes")

    assert result["folder_id"] == "folder-existing"
    actions = [call[0] for call in fake.calls]
    assert "GOOGLEDRIVE_CREATE_FOLDER" not in actions, "must not create a duplicate folder"


async def test_ensure_folder_creates_when_none_found():
    fake = FakeComposio(
        {
            "GOOGLEDRIVE_FIND_FILE": {"files": []},
            "GOOGLEDRIVE_CREATE_FOLDER": {"id": "folder-new"},
        }
    )
    client = DriveClient(tenant_id="t1", composio=fake)

    result = await client.ensure_folder("JOBOS Resumes")

    assert result["folder_id"] == "folder-new"
    action, params = fake.calls[-1]
    assert action == "GOOGLEDRIVE_CREATE_FOLDER"
    assert params["name"] == "JOBOS Resumes"


async def test_upload_resume_places_file_in_the_given_folder():
    fake = FakeComposio({"GOOGLEDRIVE_CREATE_FILE_FROM_TEXT": {"id": "f1", "webViewLink": "https://x"}})
    client = DriveClient(tenant_id="t1", composio=fake)

    await client.upload_resume(
        tenant_id="t1", filename="r.txt", text_content="b", folder_id="folder-123"
    )

    _, params = fake.calls[-1]
    assert params["parent_id"] == "folder-123"
