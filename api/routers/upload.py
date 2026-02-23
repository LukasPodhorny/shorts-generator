import os
import uuid
import boto3
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from api.auth import get_current_user
from api.models import UploadResponse

router = APIRouter(prefix="/api", tags=["upload"])


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user_token: dict = Depends(get_current_user),
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    try:
        uid = user_token["uid"]
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

        return UploadResponse(filename=file.filename, url=url, key=key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
