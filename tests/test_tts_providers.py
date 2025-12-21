import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.tts.tts_providers import F5TTS, LemonFoxTTS, TTSResult
from aishorts.modules.script.script import Reel, Block


# Mock Voice and Avatar classes for testing as avatar.py is not in context
class MockVoice:
    def __init__(
        self, provider, sample_url=None, sample_transcript=None, voice_id=None
    ):
        self.provider = provider
        self.sample_url = sample_url
        self.sample_transcript = sample_transcript
        self.voice_id = voice_id


class MockAvatar:
    def __init__(self, name, voice):
        self.name = name
        self.voice = voice


@pytest.fixture
def mock_f5_avatar():
    voice = MockVoice(
        provider="f5tts",
        sample_url="http://example.com/sample.mp3",
        sample_transcript="hello world",
    )
    return MockAvatar(name="TestF5", voice=voice)


@pytest.fixture
def mock_lemon_avatar():
    voice = MockVoice(provider="lemonfox", voice_id="lemon-voice-1")
    return MockAvatar(name="TestLemon", voice=voice)


@pytest.fixture
def mock_reel(mock_f5_avatar, mock_lemon_avatar):
    return Reel(
        title="Test Reel",
        description="A test reel.",
        blocks=[
            Block(type="dialogue", avatar=mock_f5_avatar.name, text="F5 says hi"),
            Block(type="dialogue", avatar=mock_lemon_avatar.name, text="Lemon says hi"),
        ],
    )


# --- F5TTS Tests ---


@patch.dict(os.environ, {"F5TTS_ENDPOINT_ID": "test-endpoint"})
@patch("aishorts.modules.tts.tts_providers.EndpointCaller.__init__")
def test_f5tts_init(mock_caller_init, mock_f5_avatar):
    tts = F5TTS(avatars=[mock_f5_avatar], api_key="test-key")
    mock_caller_init.assert_called_once_with(
        endpoint_id="test-endpoint", timeout=600, api_key="test-key"
    )
    assert tts.avatars == [mock_f5_avatar]


def test_f5tts_prepare_reel_input(mock_f5_avatar, mock_lemon_avatar, mock_reel):
    tts = F5TTS(avatars=[mock_f5_avatar, mock_lemon_avatar])
    prepared_input = tts._prepare_reel_input(mock_reel)
    expected = {
        "input": {
            "voices": {
                "TestF5": {
                    "voice_reference": "http://example.com/sample.mp3",
                    "ref_text": "hello world",
                }
            },
            "dialogues": [{"voice": "TestF5", "text": "F5 says hi", "id": 0}],
        }
    }
    assert prepared_input == expected


@pytest.mark.asyncio
@patch("aishorts.modules.tts.tts_providers.download_from_url", new_callable=AsyncMock)
async def test_f5tts_generate_reel_dialogues(mock_download, mock_f5_avatar, mock_reel):
    tts = F5TTS(avatars=[mock_f5_avatar])
    tts.run_async = AsyncMock(
        return_value=[{"audio_url": "http://result.mp3", "id": 0}]
    )
    mock_download.return_value = "/local/path.mp3"

    results = await tts.generate_reel_dialogues(mock_reel)

    tts.run_async.assert_called_once()
    assert len(results) == 1
    assert results[0].filepath == "/local/path.mp3"
    assert results[0].avatar.name == "TestF5"
    assert results[0].id == 0


# --- LemonFoxTTS Tests ---


@patch("aishorts.modules.tts.tts_providers.CloudflareR2")
def test_lemonfox_init(MockR2, mock_lemon_avatar):
    tts = LemonFoxTTS(avatars=[mock_lemon_avatar], api_key="test-key")
    assert tts.api_key == "test-key"
    MockR2.assert_called_once()


@pytest.mark.asyncio
@patch("aishorts.modules.tts.tts_providers.aiohttp.ClientSession")
@patch("aishorts.modules.tts.tts_providers.CloudflareR2")
@patch("builtins.open")
async def test_lemonfox_generate_voice(
    mock_open, MockR2, MockSession, mock_lemon_avatar
):
    mock_r2_instance = MockR2.return_value
    mock_r2_instance.upload_file.return_value = "http://r2/url.mp3"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read.return_value = b"audio_data"

    mock_session_instance = MockSession.return_value.__aenter__.return_value
    # FIX: Explicitly mock post as MagicMock so it works as a context manager
    mock_session_instance.post = MagicMock()
    mock_session_instance.post.return_value.__aenter__.return_value = mock_response

    tts = LemonFoxTTS(avatars=[mock_lemon_avatar])
    result = await tts.generate_voice("test text", id=5)

    assert isinstance(result, TTSResult)
    assert result.url == "http://r2/url.mp3"
    assert result.id == 5
    mock_r2_instance.upload_file.assert_called_once()
    mock_open.assert_called_once()


@pytest.mark.asyncio
@patch("aishorts.modules.tts.tts_providers.aiohttp.ClientSession")
@patch("aishorts.modules.tts.tts_providers.CloudflareR2")
@patch("builtins.open")
async def test_lemonfox_generate_reel_dialogues(
    mock_open, MockR2, MockSession, mock_lemon_avatar, mock_reel
):
    mock_r2_instance = MockR2.return_value
    mock_r2_instance.upload_file.return_value = "http://r2/url.mp3"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read.return_value = b"audio_data"

    mock_session_instance = MockSession.return_value.__aenter__.return_value
    # FIX: Explicitly mock post as MagicMock so it works as a context manager
    mock_session_instance.post = MagicMock()
    mock_session_instance.post.return_value.__aenter__.return_value = mock_response

    # The reel has one block for a lemonfox avatar
    tts = LemonFoxTTS(avatars=[mock_lemon_avatar])
    results = await tts.generate_reel_dialogues(mock_reel)

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TTSResult)
    assert result.url == "http://r2/url.mp3"
    assert result.avatar.name == "TestLemon"
    # The lemonfox block is second in the reel, so its index is 1
    assert result.id == 1
