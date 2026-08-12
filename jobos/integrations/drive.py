"""Google Drive integration via Composio, for saving tailored resumes."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.composio_client import ComposioClient

logger = structlog.get_logger(__name__)

FIND_FILE_ACTION = "GOOGLEDRIVE_FIND_FILE"
CREATE_FOLDER_ACTION = "GOOGLEDRIVE_CREATE_FOLDER"
CREATE_FILE_FROM_TEXT_ACTION = "GOOGLEDRIVE_CREATE_FILE_FROM_TEXT"

DEFAULT_RESUME_FOLDER = "JOBOS Resumes"


class DriveClient:
    """Client for saving tailored resumes to the tenant's own Google Drive."""

    def __init__(self, tenant_id: str, composio: ComposioClient | None = None) -> None:
        """Initialize the Drive client for a specific tenant.

        Args:
            tenant_id: The ID of the tenant.
            composio: Injected Composio client; constructed per-tenant if omitted.
        """
        self.tenant_id = tenant_id
        self.composio = composio or ComposioClient(tenant_id=tenant_id)
        self._logger = logger.bind(tenant_id=tenant_id)

    async def ensure_folder(self, name: str = DEFAULT_RESUME_FOLDER) -> dict[str, str]:
        """Find a folder by name, creating it only if it does not exist.

        Idempotent: calling this twice must never create a duplicate folder.

        Args:
            name: The folder name to find or create.

        Returns:
            Dict containing the real folder_id.
        """
        self._logger.info("finding_folder", name=name)
        found = await self.composio.execute(
            FIND_FILE_ACTION,
            {"query": f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}'"},
        )
        existing = found.get("files") or []
        if existing:
            folder_id = str(existing[0].get("id"))
            self._logger.info("folder_reused", folder_id=folder_id)
            return {"folder_id": folder_id}

        created = await self.composio.execute(CREATE_FOLDER_ACTION, {"name": name})
        folder_id = str(created.get("id") or "")
        self._logger.info("folder_created", folder_id=folder_id)
        return {"folder_id": folder_id}

    async def upload_resume(
        self,
        tenant_id: str,
        filename: str,
        text_content: str,
        folder_id: str | None = None,
    ) -> dict[str, str]:
        """Upload a tailored resume as a text file to Drive.

        Args:
            tenant_id: The tenant this resume belongs to (for logging).
            filename: Name for the file in Drive.
            text_content: The tailored resume body.
            folder_id: Optional destination folder; uploads to Drive root if omitted.

        Returns:
            dict containing file_id and web_view_link.

        Raises:
            ComposioActionError: if the upload failed. Never returns a success
                shape for a resume that was not actually saved.
        """
        self._logger.info("uploading_resume", tenant_id=tenant_id, filename=filename)

        params: dict[str, Any] = {"name": filename, "text_content": text_content}
        if folder_id:
            params["parent_id"] = folder_id

        data = await self.composio.execute(CREATE_FILE_FROM_TEXT_ACTION, params)
        file_id = str(data.get("id") or "")
        self._logger.info("resume_uploaded", file_id=file_id)
        return {"file_id": file_id, "web_view_link": str(data.get("webViewLink") or "")}
