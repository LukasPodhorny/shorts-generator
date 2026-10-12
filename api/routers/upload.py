import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from sqlmodel import Session, select
from api.accounts import get_or_create_user
from api.database import get_session
from api.auth import get_current_user
from api.uploads import (
    MAX_UPLOAD_SIZE,
    delete_user_upload as _delete_user_upload,
    store_uploaded_file,
)
from api.models import UploadedFile, UploadedFileRead

router = APIRouter(prefix="/api/upload", tags=["upload"])

logger = logging.getLogger(__name__)


@router.post("/", response_model=UploadedFileRead)
async def upload_file(
    file: UploadFile = File(...),
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UploadedFileRead:
    uid = user_token["uid"]
    email = user_token.get("email")

    # Ensure user exists in DB (JIT provisioning)
    get_or_create_user(session, uid, email)

    if file.size is not None and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )

    try:
        content = await file.read()
        return await store_uploaded_file(
            session, uid, file.filename or "", content, file.content_type
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("File upload failed")
        raise HTTPException(status_code=500, detail="File upload failed")


@router.get("/{file_id}", response_model=UploadedFileRead)
async def get_uploaded_file(
    file_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UploadedFileRead:
    uid = user_token["uid"]
    statement = (
        select(UploadedFile)
        .where(UploadedFile.id == file_id)
        .where(UploadedFile.user_id == uid)
    )
    file_record = session.exec(statement).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    return UploadedFileRead.model_validate(file_record, from_attributes=True)


@router.delete("/{file_id}")
async def delete_uploaded_file(
    file_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    uid = user_token["uid"]
    await _delete_user_upload(session, uid, file_id)

    return {"ok": True}
