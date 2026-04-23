import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.subtitles.subtitle_providers import (
    WhisperSubtitles,
    ElevenLabsSubtitles,
    ModalWav2VecAligner,
    _build_alignment_plan,
    _spell_integer,
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


# --- Number expansion / alignment plan ---


@pytest.mark.parametrize(
    "text, expected_aligner, expected_plan",
    [
        ("I have 50000 dollars", "i have fifty thousand dollars",
         [("I", 1), ("have", 1), ("50000", 2), ("dollars", 1)]),
        ("I have 50 000 dollars", "i have fifty thousand dollars",
         [("I", 1), ("have", 1), ("50 000", 2), ("dollars", 1)]),
        ("That costs 50000$", "that costs fifty thousand",
         [("That", 1), ("costs", 1), ("50000$", 2)]),
        ("That costs 50 000 $", "that costs fifty thousand",
         [("That", 1), ("costs", 1), ("50 000", 2)]),
        ("Remember 2026", "remember two thousand twenty six",
         [("Remember", 1), ("2026", 4)]),
        ("On 9/11 everything changed", "on nine eleven everything changed",
         [("On", 1), ("9/11", 2), ("everything", 1), ("changed", 1)]),
        ("2 000 000 people", "two million people",
         [("2 000 000", 2), ("people", 1)]),
        ("no numbers here", "no numbers here",
         [("no", 1), ("numbers", 1), ("here", 1)]),
        ("", "", []),
        ("!!!", "", []),
    ],
)
def test_build_alignment_plan(text, expected_aligner, expected_plan):
    aligner_text, plan = _build_alignment_plan(text)
    assert aligner_text == expected_aligner
    assert plan == expected_plan
    # Invariant: the aligner word count equals the sum of plan absorption counts.
    assert len(aligner_text.split()) == sum(n for _, n in plan)


def test_spell_integer_strips_and_and_hyphens():
    assert _spell_integer("2026") == ["two", "thousand", "twenty", "six"]
    assert _spell_integer("1234567") == [
        "one", "million", "two", "hundred", "thirty", "four",
        "thousand", "five", "hundred", "sixty", "seven",
    ]


def _make_aligner():
    with patch(
        "aishorts.modules.subtitles.subtitle_providers.CloudflareR2"
    ):
        return ModalWav2VecAligner(
            endpoint_url="https://fake-endpoint.modal.run",
            min_silence_duration=0.5,
        )


def test_plan_to_words_merges_digit_spans():
    aligner = _make_aligner()
    plan = [("I", 1), ("have", 1), ("50000", 2), ("dollars", 1)]
    segments = [
        {"word": "i",       "start": 0.0, "end": 0.2},
        {"word": "have",    "start": 0.3, "end": 0.5},
        {"word": "fifty",   "start": 0.6, "end": 0.9},
        {"word": "thousand","start": 0.9, "end": 1.3},
        {"word": "dollars", "start": 1.4, "end": 1.8},
    ]
    words = aligner._plan_to_words(plan, segments)

    assert [w.word for w in words] == ["I", "have", "50000", "dollars"]
    # '50000' span covers fifty->thousand.
    num = words[2]
    assert num.start == 0.6
    # end is stitched forward to 'dollars' start (gap 1.4-1.3 = 0.1 < 0.5).
    assert num.end == 1.4


def test_plan_to_words_raises_on_span_count_mismatch():
    aligner = _make_aligner()
    plan = [("hello", 1), ("2026", 4)]
    segments = [{"word": "hello", "start": 0.0, "end": 0.5}]  # 1 instead of 5
    with pytest.raises(ValueError, match="plan expected"):
        aligner._plan_to_words(plan, segments)


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
