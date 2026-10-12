"""Shared per-user upload helpers used by both REST routers and the MCP server."""

import io
import logging
import os
import uuid
from typing import BinaryIO

import boto3
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from api.file_conversion import (
    LEGACY_OFFICE_EXTENSIONS,
    ConversionError,
    convert_office_to_pdf,
)
from api.models import UploadedFile, UploadedFileRead

logger = logging.getLogger(__name__)

# Everything below (except the legacy office formats) is converted to Markdown
# by the ingest layer (MarkItDown) at generation time.
ALLOWED_EXTENSIONS = {
    # documents
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".epub",
    ".ipynb",
    ".msg",
    # images (described via vision LLM)
    ".jpg",
    ".jpeg",
    ".png",
    # audio (transcribed)
    ".mp3",
    ".wav",
    ".m4a",
} | LEGACY_OFFICE_EXTENSIONS

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


def list_user_uploads(session: Session, uid: str) -> list[UploadedFileRead]:
    """Return the user's uploaded source files, newest first."""
    statement = (
        select(UploadedFile)
        .where(UploadedFile.user_id == uid)
        .order_by(UploadedFile.created_at.desc())  # pyright: ignore[reportAttributeAccessIssue] -- SQLAlchemy column at runtime; checker sees datetime
    )
    return [
        UploadedFileRead.model_validate(f, from_attributes=True)
        for f in session.exec(statement).all()
    ]


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


async def store_uploaded_file(
    session: Session,
    uid: str,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> UploadedFileRead:
    """Validate, optionally convert, upload to R2, and record one file.

    Shared by REST multipart upload and the MCP base64 upload tool.
    Raises HTTPException(400) for bad type/conversion, 413 when too large.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is missing")

    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )

    stored_filename = filename
    stored_ext = file_ext
    stored_content_type = content_type or "application/octet-stream"
    upload_body: BinaryIO

    if file_ext in LEGACY_OFFICE_EXTENSIONS:
        # Convert legacy office docs (which MarkItDown can't read) to PDF.
        try:
            pdf_bytes = await convert_office_to_pdf(content, filename)
        except ConversionError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to convert document to PDF: {str(e)}",
            )
        upload_body = io.BytesIO(pdf_bytes)
        stored_ext = ".pdf"
        stored_filename = os.path.splitext(filename)[0] + ".pdf"
        stored_content_type = "application/pdf"
    else:
        upload_body = io.BytesIO(content)

    key = f"uploads/{uid}/{uuid.uuid4()}{stored_ext}"

    s3_client = _r2_client()
    bucket_name = os.getenv("R2_BUCKET")

    # Upload file object directly to R2 (running in threadpool to avoid blocking)
    await run_in_threadpool(s3_client.upload_fileobj, upload_body, bucket_name, key)

    # Generate a presigned URL for immediate access
    url = await run_in_threadpool(
        s3_client.generate_presigned_url,
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=604800,  # 7 days
    )

    uploaded_file = UploadedFile(
        filename=stored_filename,
        url=url,
        key=key,
        content_type=stored_content_type,
        user_id=uid,
    )
    session.add(uploaded_file)
    session.commit()
    session.refresh(uploaded_file)

    return UploadedFileRead.model_validate(uploaded_file, from_attributes=True)


async def delete_user_upload(session: Session, uid: str, file_id: int) -> None:
    """Delete one of the user's uploads from R2 and the DB, else 404."""
    statement = (
        select(UploadedFile)
        .where(UploadedFile.id == file_id)
        .where(UploadedFile.user_id == uid)
    )
    file_record = session.exec(statement).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        s3_client = _r2_client()
        bucket_name = os.getenv("R2_BUCKET")
        await run_in_threadpool(
            s3_client.delete_object, Bucket=bucket_name, Key=file_record.key
        )
    except Exception:
        logger.exception("Failed to delete file from storage")
        raise HTTPException(
            status_code=500, detail="Failed to delete file from storage"
        )

    session.delete(file_record)
    session.commit()
