import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.utils.r2_handler import (
    CloudflareR2,
    download_from_url,
    BucketConfiguration,
)


@pytest.fixture
def r2_client():
    with patch("aishorts.utils.r2_handler.boto3.client") as mock_boto:
        config = BucketConfiguration(bucket="test-bucket")
        r2 = CloudflareR2(config)
        r2.client = mock_boto.return_value
        yield r2


def test_upload_file(r2_client):
    r2_client.client.generate_presigned_url.return_value = "http://presigned"

    url = r2_client.upload_file("local.txt", "remote.txt")

    r2_client.client.upload_file.assert_called_with(
        "local.txt", "test-bucket", "remote.txt"
    )
    assert url == "http://presigned"


def test_delete_file(r2_client):
    r2_client.delete_file("key")
    r2_client.client.delete_object.assert_called_with(Bucket="test-bucket", Key="key")


@pytest.mark.asyncio
@patch("aishorts.utils.r2_handler.aiohttp.ClientSession")
@patch("aishorts.utils.r2_handler.aiofiles.open")
async def test_download_from_url(mock_open, mock_session):
    # Mock response
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()

    # Mock content iteration
    async def iter_chunked(n):
        yield b"chunk"

    mock_resp.content.iter_chunked = iter_chunked

    # Mock session context manager
    mock_session_inst = mock_session.return_value.__aenter__.return_value
    mock_session_inst.get = MagicMock()
    mock_session_inst.get.return_value.__aenter__.return_value = mock_resp

    # Mock file
    mock_file = AsyncMock()
    mock_open.return_value.__aenter__.return_value = mock_file

    path = await download_from_url("http://example.com/file.png", path="/tmp")

    assert "/tmp" in path
    assert ".png" in path
    mock_file.write.assert_called_with(b"chunk")
