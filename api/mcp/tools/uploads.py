"""Upload tools: the caller's source files (list, upload, delete)."""

import base64
import binascii
import mimetypes

from fastmcp.exceptions import ToolError

from api.mcp.auth import current_user_token, require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors
from api.uploads import (
    delete_user_upload as _delete_user_upload,
    list_user_uploads as _list_user_uploads,
    store_uploaded_file,
)


def list_my_uploads() -> list[dict]:
    """List the caller's uploaded source documents, newest first.

    Pass an entry's `key` in `generate_reels(files=[...])` to use that
    document as source material. Only files listed here may be referenced.
    """
    with mcp_errors("list_my_uploads"):
        require_scope("read")
        token = current_user_token()
        with session_scope() as session:
            return [
                f.model_dump(mode="json")
                for f in _list_user_uploads(session, token["uid"])
            ]


async def upload_file(filename: str, content_base64: str) -> dict:
    """Upload a source document for use in generations.

    Args:
        filename: File name with extension (pdf, docx, txt, md, images,
            audio, ...). Legacy office formats are converted to PDF.
        content_base64: The file bytes, base64-encoded. Decoded size limit
            is 50 MB.

    Returns the stored file (id, key, url). Pass its `key` in
    `generate_reels(files=[...])`.
    """
    with mcp_errors("upload_file"):
        require_scope("write")
        token = current_user_token()
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ToolError("content_base64 is not valid base64") from None
        content_type, _ = mimetypes.guess_type(filename)
        with session_scope() as session:
            stored = await store_uploaded_file(
                session, token["uid"], filename, content, content_type
            )
            return stored.model_dump(mode="json")


async def delete_my_upload(file_id: int) -> dict:
    """Delete one of the caller's uploaded source files."""
    with mcp_errors("delete_my_upload"):
        require_scope("write")
        token = current_user_token()
        with session_scope() as session:
            await _delete_user_upload(session, token["uid"], file_id)
            return {"ok": True}
