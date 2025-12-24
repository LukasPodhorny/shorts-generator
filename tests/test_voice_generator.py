import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.script.script import Reel, Block
from aishorts.modules.tts.tts_providers import TTSResult


# Mock Voice and Avatar classes for testing as avatar.py is not in context
class MockVoice:
    def __init__(self, provider):
        self.provider = provider


class MockAvatar:
    def __init__(self, name, provider):
        self.name = name
        self.voice = MockVoice(provider)


@pytest.fixture
def mock_avatars():
    """Provides a list of mock avatars with different TTS providers."""
    return [
        MockAvatar("Alice", "f5tts"),
        MockAvatar("Bob", "lemonfox"),
        MockAvatar("Charlie", "f5tts"),
    ]


@pytest.fixture
def mock_reel():
    """Provides a mock Reel object for testing dialogue generation."""
    return Reel(
        title="Test Reel",
        description="A test reel.",
        blocks=[
            Block(type="dialogue", avatar="Alice", text="Hello Alice!"),
            Block(type="dialogue", avatar="Bob", text="Hi Bob!"),
        ],
    )


@patch("aishorts.modules.tts.voice_generator.TTSProvider.get")
def test_voice_generator_init(mock_get_provider, mock_avatars):
    """Tests that VoiceGenerator initializes the correct set of provider classes."""
    mock_f5_cls = MagicMock(name="F5TTS_cls")
    mock_lemon_cls = MagicMock(name="LemonFox_cls")
    mock_get_provider.side_effect = lambda p: {
        "f5tts": mock_f5_cls,
        "lemonfox": mock_lemon_cls,
    }.get(p)

    vg = VoiceGenerator(
        avatars=mock_avatars,
        tts_f5tts_api_key="f5_key",
        tts_lemonfox_api_key="lemon_key",
    )

    assert len(vg.provider_instances) == 2
    mock_f5_cls.assert_called_once_with(
        avatars=mock_avatars,
        tts_f5tts_api_key="f5_key",
        tts_lemonfox_api_key="lemon_key",
    )
    mock_lemon_cls.assert_called_once_with(
        avatars=mock_avatars,
        tts_f5tts_api_key="f5_key",
        tts_lemonfox_api_key="lemon_key",
    )


@pytest.mark.asyncio
@patch("aishorts.modules.tts.voice_generator.TTSProvider.get")
async def test_generate_voice(mock_get_provider, mock_avatars):
    """Tests that generate_voice correctly calls the first provider instance."""
    mock_provider_instance = MagicMock()
    mock_provider_instance.generate_voice = AsyncMock(return_value="audio_path")
    mock_get_provider.return_value = MagicMock(return_value=mock_provider_instance)

    vg = VoiceGenerator(avatars=[mock_avatars[0]])
    result = await vg.generate_voice("hello world", id=1, some_kwarg="value")

    assert result == "audio_path"
    mock_provider_instance.generate_voice.assert_called_once_with(
        "hello world", 1, some_kwarg="value"
    )


@pytest.mark.asyncio
@patch("aishorts.modules.tts.voice_generator.TTSProvider.get")
async def test_generate_reel_dialogues(mock_get_provider, mock_avatars, mock_reel):
    """Tests that reel dialogues are generated concurrently and results are aggregated and sorted."""
    mock_f5_instance = MagicMock()
    f5_result = TTSResult(id=0, filepath="f5.mp3")
    mock_f5_instance.generate_reel_dialogues = AsyncMock(return_value=[f5_result])

    mock_lemon_instance = MagicMock()
    lemon_result = TTSResult(id=1, filepath="lemon.mp3")
    mock_lemon_instance.generate_reel_dialogues = AsyncMock(return_value=[lemon_result])

    # FIX: Define class mocks outside lambda so they are stable
    mock_f5_cls = MagicMock(return_value=mock_f5_instance)
    mock_lemon_cls = MagicMock(return_value=mock_lemon_instance)

    mock_get_provider.side_effect = lambda p: {
        "f5tts": mock_f5_cls,
        "lemonfox": mock_lemon_cls,
    }.get(p)

    vg = VoiceGenerator(avatars=mock_avatars)
    results = await vg.generate_reel_dialogues(mock_reel, some_kwarg="value")

    mock_f5_instance.generate_reel_dialogues.assert_called_once_with(
        mock_reel, some_kwarg="value"
    )
    mock_lemon_instance.generate_reel_dialogues.assert_called_once_with(
        mock_reel, some_kwarg="value"
    )

    assert len(results) == 2
    assert results == sorted([f5_result, lemon_result])
