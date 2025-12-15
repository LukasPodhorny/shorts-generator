import boto3
import os
from urllib.parse import urlparse
import uuid
import requests
from pydantic import BaseModel


class BucketConfiguration(BaseModel):
    endponit_url: str | None = None
    aws_acces_key_id: str | None = None
    aws_secret_acces_key: str | None = None
    bucket: str | None = None
    output_dir: str | None = None


class CloudflareR2:
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

    def upload_file(self, file_path: str, key: str) -> str:
        """Uploads file and returns its presigned URL."""
        self.client.upload_file(file_path, self.bucket, key)
        return self.create_presigned_url(key)

    def create_presigned_url(self, key: str, expires_in=604800) -> str:
        """Generates a temporary download link."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_file(self, key: str):
        """Deletes an object from the bucket."""
        self.client.delete_object(Bucket=self.bucket, Key=key)

    @staticmethod
    def get_key_from_url(url: str) -> str:
        parsed = urlparse(url)
        return parsed.path.lstrip("/")

    @staticmethod
    def get_random_filepath(base_path: str, ext: str):
        filename = f"{uuid.uuid4().hex}{ext}"

        filepath = os.path.join(base_path, filename)

        return filepath

    @staticmethod
    def download_presigned_file(url: str, path: str = "", ext: str = None) -> str:
        """
        Downloads a file from a presigned URL into outputs/{uuid}.{ext}
        and returns the local file path.
        """

        # Extract filename extension from the URL
        url_path = urlparse(url).path
        ext = ext or os.path.splitext(url_path)[1] or ".bin"

        # Create unique filename
        filepath = CloudflareR2.get_random_filepath(path, ext)

        # Download
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return filepath
