"""
Backfills thumbnail_url for VideoTemplate rows that have preview_url but no thumbnail_url.

Usage:
    python -m api.backfill_thumbnails           # backfill only missing
    python -m api.backfill_thumbnails --force   # regenerate all (where preview_url is set)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

import boto3
import requests
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.append(os.getcwd())

from api.database import engine
from api.models import VideoTemplate

load_dotenv()


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "template"


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _public_url(key: str) -> str:
    domain = os.getenv("R2_PUBLIC_DOMAIN")
    if domain:
        return f"https://{domain}/{key}"
    return _r2_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": os.getenv("R2_BUCKET"), "Key": key},
        ExpiresIn=604800,
    )


def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)


def _extract_thumbnail(video_path: str, thumb_path: str) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "3",
            thumb_path,
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not os.path.exists(thumb_path):
        raise RuntimeError(
            f"ffmpeg failed: {result.stderr.decode(errors='ignore')[-500:]}"
        )


def process_template(template: VideoTemplate) -> str:
    bucket = os.getenv("R2_BUCKET")
    if not bucket:
        raise RuntimeError("R2_BUCKET is not configured")

    slug = _slug(template.name)
    tmp_dir = tempfile.mkdtemp(prefix="tpl_backfill_")
    try:
        video_path = os.path.join(tmp_dir, f"{slug}.mp4")
        thumb_path = os.path.join(tmp_dir, f"{slug}.jpg")

        _download(template.preview_url, video_path)
        _extract_thumbnail(video_path, thumb_path)

        thumb_key = f"templates/{slug}.jpg"
        _r2_client().upload_file(
            thumb_path, bucket, thumb_key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )
        return _public_url(thumb_key)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate thumbnails even when one already exists",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        stmt = select(VideoTemplate).where(VideoTemplate.preview_url.is_not(None))
        if not args.force:
            stmt = stmt.where(VideoTemplate.thumbnail_url.is_(None))

        templates = session.exec(stmt).all()
        if not templates:
            print("Nothing to backfill.")
            return

        print(f"Backfilling {len(templates)} template(s)...")
        for t in templates:
            try:
                url = process_template(t)
                t.thumbnail_url = url
                session.add(t)
                session.commit()
                print(f"  [OK] {t.name} -> {url}")
            except Exception as e:
                session.rollback()
                print(f"  [FAIL] {t.name}: {e}")


if __name__ == "__main__":
    main()
