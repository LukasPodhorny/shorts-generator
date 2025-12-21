import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.subtitles.subtitle_providers import (
    WhisperSubtitles,
    ElevenLabsSubtitles,
    get_wav_length,
)
from openai.types.audio import TranscriptionVerbose
from aishorts.modules.tts.tts_providers import TTSResult


# --- Helper Tests ---


@patch("aishorts.modules.subtitles.subtitle_providers.AudioSegment")
def test_get_wav_length(mock_audio_segment):
    mock_audio = MagicMock()
    mock_audio.__len__.return_value = 5000  # 5 seconds
    mock_audio_segment.from_wav.return_value = mock_audio

    duration = get_wav_length("test.wav")
    assert duration == 5.0
    mock_audio_segment.from_wav.assert_called_once_with("test.wav")


# --- WhisperSubtitles Tests ---


class ConcreteWhisperSubtitles(WhisperSubtitles):
    provider_name = None

    async def generate_multiple_subtitles(self, tts_results):
        return []


@pytest.fixture
def whisper_provider():
    with patch(
        "aishorts.modules.subtitles.subtitle_providers.AsyncOpenAI"
    ) as mock_client_cls:
        provider = ConcreteWhisperSubtitles(api_key="test_key", use_lemonfox=True)
        provider.client = mock_client_cls.return_value
        return provider


@pytest.mark.asyncio
@patch("builtins.open", new_callable=MagicMock)
async def test_whisper_generate_subtitles(mock_open, whisper_provider):
    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file

    mock_transcription = MagicMock(spec=TranscriptionVerbose)
    whisper_provider.client.audio.transcriptions.create = AsyncMock(
        return_value=mock_transcription
    )

    result = await whisper_provider.generate_subtitles("audio.wav")

    assert result == mock_transcription
    whisper_provider.client.audio.transcriptions.create.assert_called_once()
    call_kwargs = whisper_provider.client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"
    assert call_kwargs["file"] == mock_file


# --- ElevenLabsSubtitles Tests ---


@pytest.fixture
def elevenlabs_provider():
    with patch(
        "aishorts.modules.subtitles.subtitle_providers.ElevenLabs"
    ) as mock_client_cls:
        provider = ElevenLabsSubtitles(api_key="test_key")
        provider.elevenlabs = mock_client_cls.return_value
        return provider


@pytest.mark.asyncio
@patch("aishorts.modules.subtitles.subtitle_providers.get_wav_length")
@patch("builtins.open", new_callable=MagicMock)
async def test_elevenlabs_generate_subtitles(
    mock_open, mock_get_length, elevenlabs_provider
):
    mock_get_length.return_value = 10.0
    mock_open.return_value.__enter__.return_value.read.return_value = b"audio_data"

    # Mock response from forced_alignment
    mock_alignment = MagicMock()
    w1 = MagicMock(text="Hello", start=0.0, end=1.0)
    w2 = MagicMock(text="World", start=1.5, end=2.5)
    mock_alignment.words = [w1, w2]

    # Mock the sync call wrapped in to_thread
    elevenlabs_provider.elevenlabs.forced_alignment.create.return_value = mock_alignment

    result = await elevenlabs_provider.generate_subtitles("audio.wav", "Hello World")

    assert isinstance(result, TranscriptionVerbose)
    assert result.duration == 10.0
    assert len(result.words) == 2
    assert result.words[0].word == "Hello"
    assert result.words[1].word == "World"


@pytest.mark.asyncio
@patch("aishorts.modules.subtitles.subtitle_providers.get_wav_length")
@patch("builtins.open", new_callable=MagicMock)
async def test_elevenlabs_silence_handling(
    mock_open, mock_get_length, elevenlabs_provider
):
    """Test that short silences extend the previous word's duration."""
    mock_get_length.return_value = 5.0
    mock_open.return_value.__enter__.return_value.read.return_value = b"data"

    mock_alignment = MagicMock()

    # Word 1: "Hello" (0.0 - 1.0)
    w1 = MagicMock(text="Hello", start=0.0, end=1.0)
    # Word 2: "" (Silence) (1.0 - 1.2) -> duration 0.2 < 0.5 (default min_silence)
    w2 = MagicMock(text=" ", start=1.0, end=1.2)
    # Word 3: "World" (1.2 - 2.0)
    w3 = MagicMock(text="World", start=1.2, end=2.0)

    mock_alignment.words = [w1, w2, w3]
    elevenlabs_provider.elevenlabs.forced_alignment.create.return_value = mock_alignment

    result = await elevenlabs_provider.generate_subtitles("f.wav", "txt")

    # w2 should be skipped, and w1 extended to cover the silence
    assert len(result.words) == 2
    assert result.words[0].word == "Hello"
    assert result.words[0].end == 1.2  # Extended
    assert result.words[1].word == "World"


@pytest.mark.asyncio
async def test_elevenlabs_generate_multiple_subtitles(elevenlabs_provider):
    # Mock generate_subtitles to avoid complex setup
    elevenlabs_provider.generate_subtitles = AsyncMock(side_effect=["sub1", "sub2"])

    tts_results = [
        MagicMock(filepath="f1.wav", transcription="t1"),
        MagicMock(filepath="f2.wav", transcription="t2"),
    ]

    results = await elevenlabs_provider.generate_multiple_subtitles(tts_results)

    assert results == ["sub1", "sub2"]
    assert elevenlabs_provider.generate_subtitles.call_count == 2
