import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from aishorts.modules.lipsync.lipsync_providers import LipsyncResult


class MockAvatar:
    def __init__(self, name, lipsync_provider):
        self.name = name
        self.lipsync_provider = lipsync_provider


@pytest.fixture
def mock_avatars():
    return [MockAvatar("A", "float"), MockAvatar("B", "float")]


@patch("aishorts.modules.lipsync.lipsync_generator.LipsyncProvider.get")
def test_init(mock_get, mock_avatars):
    # Setup mock class
    mock_cls = MagicMock()
    mock_get.return_value = mock_cls

    gen = LipsyncGenerator(mock_avatars)

    # Since both avatars use "float", set() should deduplicate, resulting in 1 provider instance
    assert len(gen.provider_instances) == 1
    mock_cls.assert_called_once()
    # Verify avatars were passed to constructor
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["avatars"] == mock_avatars


@pytest.mark.asyncio
@patch("aishorts.modules.lipsync.lipsync_generator.LipsyncProvider.get")
@patch("aishorts.modules.lipsync.lipsync_generator.await_or_thread")
async def test_generate_lipsync(mock_await, mock_get, mock_avatars):
    # Setup provider instance
    mock_instance = MagicMock()
    mock_instance.generate_lipsync = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    # Mock await_or_thread to return a result directly (simulating async result)
    mock_await.side_effect = lambda func, *args, **kwargs: LipsyncResult(
        id=1, url="url"
    )

    gen = LipsyncGenerator(mock_avatars)
    result = await gen.generate_lipsync("audio_url", id=1)

    assert result.id == 1
    assert result.url == "url"
    # Ensure await_or_thread was called with the provider's method
    mock_await.assert_called_once()
    assert mock_await.call_args[0][0] == mock_instance.generate_lipsync


@pytest.mark.asyncio
@patch("aishorts.modules.lipsync.lipsync_generator.LipsyncProvider.get")
@patch("aishorts.modules.lipsync.lipsync_generator.await_or_thread")
async def test_generate_lipsyncs(mock_await, mock_get, mock_avatars):
    # Setup provider instance
    mock_instance = MagicMock()
    mock_instance.generate_lipsyncs = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    # Mock await_or_thread to return a list of results (as a coroutine/future)
    async def mock_runner(func, *args, **kwargs):
        return [LipsyncResult(id=1), LipsyncResult(id=2)]

    mock_await.side_effect = mock_runner

    gen = LipsyncGenerator(mock_avatars)
    results = await gen.generate_lipsyncs([])

    assert len(results) == 2
    assert results[0].id == 1
    assert results[1].id == 2
    mock_await.assert_called_once()
