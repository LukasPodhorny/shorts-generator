import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.provider import Provider, MediaFile


# --- Provider Registry Tests ---


def test_provider_registry_isolation():
    """Test that different provider types maintain separate registries."""

    # Define base provider types (like TTSProvider, ImageProvider)
    class BaseTypeA(Provider):
        pass

    class BaseTypeB(Provider):
        pass

    # Register implementations
    class ImplA1(BaseTypeA):
        provider_name = "a1"

    class ImplB1(BaseTypeB):
        provider_name = "b1"

    # Check isolation
    assert "a1" in BaseTypeA.list_names()
    assert "b1" not in BaseTypeA.list_names()

    assert "b1" in BaseTypeB.list_names()
    assert "a1" not in BaseTypeB.list_names()


def test_provider_registration():
    """Test basic registration and retrieval."""

    class TestBase(Provider):
        pass

    class TestImpl(TestBase):
        provider_name = "test_impl"

    assert TestBase.get("test_impl") == TestImpl
    assert "test_impl" in TestBase.list_names()


def test_provider_duplicate_registration():
    """Test that registering duplicate names raises ValueError."""

    class TestBase(Provider):
        pass

    class TestImpl1(TestBase):
        provider_name = "dup"

    with pytest.raises(ValueError, match="already registered"):

        class TestImpl2(TestBase):
            provider_name = "dup"


def test_provider_get_unknown():
    """Test retrieving a non-existent provider."""

    class TestBase(Provider):
        pass

    with pytest.raises(ValueError, match="Unknown TestBase"):
        TestBase.get("non_existent")


def test_abstract_provider_no_registration():
    """Test that classes without provider_name are not registered."""

    class TestBase(Provider):
        pass

    class AbstractImpl(TestBase):
        # No provider_name set
        pass

    assert AbstractImpl not in TestBase._registry.values()


# --- MediaFile Tests ---


@pytest.mark.asyncio
@patch("aishorts.modules.provider.aiohttp.ClientSession")
@patch("aishorts.modules.provider.aiofiles.open")
@patch("os.makedirs")
@patch("os.path.exists")
async def test_media_file_download(mock_exists, mock_makedirs, mock_open, mock_session):
    # Setup mocks
    mock_exists.return_value = False

    mock_resp = AsyncMock()
    mock_resp.read.return_value = b"data"
    # Mock the context manager chain: session.get() -> response
    mock_session_instance = mock_session.return_value.__aenter__.return_value
    mock_session_instance.get = MagicMock()
    mock_session_instance.get.return_value.__aenter__.return_value = mock_resp

    mock_file = AsyncMock()
    mock_open.return_value.__aenter__.return_value = mock_file

    media = MediaFile(id=1, url="http://example.com/image.png")

    # Execute
    path = await media.ensure_local_async("/tmp")

    # Verify
    assert "image.png" in path
    mock_makedirs.assert_called_with("/tmp", exist_ok=True)
    mock_resp.read.assert_called_once()
    mock_file.write.assert_called_with(b"data")
    assert media.path == path
