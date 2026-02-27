import os
import uuid
import boto3
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select
from api.database import get_session
from api.auth import get_current_user
from api.models import UploadedFile, UploadedFileRead, User

router = APIRouter(prefix="/api/upload", tags=["upload"])


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt"}


@router.post("/", response_model=UploadedFileRead)
async def upload_file(
    file: UploadFile = File(...),
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UploadedFileRead:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    uid = user_token["uid"]
    email = user_token.get("email")

    # Ensure user exists in DB (JIT provisioning)
    user = session.get(User, uid)
    if not user:
        user = User(id=uid, email=email, credits=10)
        session.add(user)
        session.commit()

    try:
        key = f"uploads/{uid}/{uuid.uuid4()}{file_ext}"

        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        bucket_name = os.getenv("R2_BUCKET")

        # Upload file object directly to R2 (running in threadpool to avoid blocking)
        await run_in_threadpool(s3_client.upload_fileobj, file.file, bucket_name, key)

        # Generate a presigned URL for immediate access
        url = await run_in_threadpool(
            s3_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=604800,  # 7 days
        )

        # Save to Database
        uploaded_file = UploadedFile(
            filename=file.filename,
            url=url,
            key=key,
            content_type=file.content_type or "application/octet-stream",
            user_id=uid,
        )
        session.add(uploaded_file)
        session.commit()
        session.refresh(uploaded_file)

        return uploaded_file
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


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

    return file_record


@router.delete("/{file_id}")
async def delete_uploaded_file(
    file_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    uid = user_token["uid"]
    statement = (
        select(UploadedFile)
        .where(UploadedFile.id == file_id)
        .where(UploadedFile.user_id == uid)
    )
    file_record = session.exec(statement).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete from R2
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        bucket_name = os.getenv("R2_BUCKET")
        await run_in_threadpool(
            s3_client.delete_object, Bucket=bucket_name, Key=file_record.key
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete file from storage: {str(e)}"
        )

    # Delete from DB
    session.delete(file_record)
    session.commit()

    return {"ok": True}
