import boto3
import os
from urllib.parse import urlparse
import uuid
import aiohttp
from pydantic import BaseModel
import asyncio
import aiofiles
from typing import Union, Optional


class BucketConfiguration(BaseModel):
    endponit_url: str | None = None
    aws_acces_key_id: str | None = None
    aws_secret_acces_key: str | None = None
    bucket: str | None = None
    output_dir: str | None = None
    public_domain: str | None = None


class CloudflareR2:
    _clock_skew: float | None = None
    _clock_skew_checked: bool = False

    def __init__(
        self, bucket_configuration: BucketConfiguration = BucketConfiguration()
    ):
        self.client = boto3.client(
            "s3",
            endpoint_url=bucket_configuration.endponit_url or os.getenv("R2_ENDPOINT"),
            aws_access_key_id=bucket_configuration.aws_acces_key_id
            or os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=bucket_configuration.aws_secret_acces_key
            or os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        self.bucket = bucket_configuration.bucket or os.getenv("R2_BUCKET")
        self.output_dir = bucket_configuration.output_dir or os.getenv(
            "CLOUDFLARE_OUTPUT_DIR", "outputs"
        )
        self.public_domain = bucket_configuration.public_domain or os.getenv(
            "R2_PUBLIC_DOMAIN"
        )
        
        # Self-correct clock skew if possible (lazy-loaded class level)
        endpoint = bucket_configuration.endponit_url or os.getenv("R2_ENDPOINT")
        self._ensure_clock_skew(endpoint)
        
        if CloudflareR2._clock_skew and abs(CloudflareR2._clock_skew) > 10:
            skew = CloudflareR2._clock_skew
            # botocore uses _client_config.clock_skew in some versions, 
            # but we also register a handler for the request-created event to be sure.
            self.client._client_config.clock_skew = skew
            
            def add_clock_skew(request, **kwargs):
                if hasattr(request, 'context'):
                    request.context['timestamp_offset'] = int(skew)

            self.client.meta.events.register('request-created.s3', add_clock_skew)

    @classmethod
    def _ensure_clock_skew(cls, endpoint: str | None):
        if cls._clock_skew_checked or not endpoint:
            return
            
        try:
            import requests
            from email.utils import parsedate_to_datetime
            from datetime import datetime, timezone

            print(f"DEBUG: Checking clock skew against {endpoint}...")
            response = requests.head(endpoint, timeout=5)
            server_date_str = response.headers.get('Date')
            if server_date_str:
                server_date = parsedate_to_datetime(server_date_str)
                local_date = datetime.now(timezone.utc)
                cls._clock_skew = (server_date - local_date).total_seconds()
                print(f"DEBUG: Detected clock skew: {cls._clock_skew} seconds.")
            cls._clock_skew_checked = True
        except Exception as e:
            print(f"DEBUG: Clock correction failed: {e}")
            cls._clock_skew_checked = True # Don't keep retrying if it fails

    def upload_file(self, file_path: str, key: str) -> str:
        """Uploads file and returns its public URL."""
        self.client.upload_file(file_path, self.bucket, key)
        return self.get_public_url(key)

    def create_presigned_url(self, key: str, expires_in=604800) -> str:
        """Generates a temporary download link."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def get_public_url(self, key: str) -> str:
        """Returns the public URL for a key. Falls back to presigned URL if public domain is not set."""
        if self.public_domain:
            return f"https://{self.public_domain}/{key}"
        return self.create_presigned_url(key)

    def copy_file(self, source_key: str, dest_key: str) -> str:
        """Copies an object within the bucket and returns its public URL."""
        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": source_key},
            Key=dest_key,
        )
        return self.get_public_url(dest_key)

    def delete_file(self, key: str):
        """Deletes an object from the bucket."""
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str):
        """Deletes all objects with a given prefix."""
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            if "Contents" in page:
                delete_keys = {
                    "Objects": [{"Key": obj["Key"]} for obj in page["Contents"]]
                }
                self.client.delete_objects(Bucket=self.bucket, Delete=delete_keys)

    @staticmethod
    def get_key_from_url(url: Union[str, dict], bucket_name: Optional[str] = None) -> str:
        """
        Extracts the R2 key from a URL string or dictionary.
        Strips the leading slash and optionally the bucket name if it's the first part of the path.
        """
        if isinstance(url, dict):
            url = url.get("url", "")
            
        if not url or not isinstance(url, str):
            return ""

        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        
        # If the path starts with the bucket name (common in S3-style URLs), strip it
        if bucket_name and path.startswith(f"{bucket_name}/"):
            path = path[len(bucket_name)+1:]
            
        return path

    @staticmethod
    def get_random_filepath(base_path: str, ext: str):
        filename = f"{uuid.uuid4().hex}{ext}"

        filepath = os.path.join(base_path, filename)

        return filepath


async def download_from_url(
    url: str | dict,
    path: str = "",
    ext: str | None = None,
    timeout: int = 600,
    full_path: str | None = None,
) -> str:
    """
    Downloads a file from a URL into outputs/{uuid}.{ext} (or full_path if provided)
    and returns the local file path. Handles dict-based URLs with 'url' and 'cache_key'.
    """
    # Extract actual URL string if it's a dict
    url_str = url
    if isinstance(url, dict):
        url_str = url.get("url")
        if not url_str:
            raise ValueError("URL dictionary missing 'url' key")
    if not isinstance(url_str, str):
        raise TypeError(f"Expected URL string, got {type(url_str).__name__}: {url_str!r}")

    if full_path:
        filepath = full_path
    else:
        # Extract filename extension from the URL
        url_path = urlparse(url_str).path
        ext = ext or os.path.splitext(url_path)[1] or ".bin"

        # Create unique filename
        filepath = CloudflareR2.get_random_filepath(path, ext)

    # Download
    timeout = aiohttp.ClientTimeout(total=timeout)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url_str) as response:
                    response.raise_for_status()
                    async with aiofiles.open(filepath, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
            break
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == 2:
                raise e
            print(f"Download failed ({attempt + 1}/3). Retrying... Error: {e}")
            await asyncio.sleep(2**attempt)

    return filepath
