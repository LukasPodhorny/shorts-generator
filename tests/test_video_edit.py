import pytest
from unittest.mock import MagicMock
from aishorts.modules.video_edit.video_edit import (
    TemplateConfig,
    SubtitleStyle,
)
from aishorts.modules.video_edit.video_edit_templates import GameplayTemplate
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from aishorts.modules.script.script import Block, ImageMedia, Trigger


class MockImageResult:
    def __init__(self, path):
        self.media = MagicMock()
        self.media.path = path


@pytest.fixture
def template():
    config = TemplateConfig(
        bg_video="bg.mp4", music="music.mp3", subtitle_style=SubtitleStyle()
    )
    return GameplayTemplate(config)


def test_convert_to_absolute_timing(template):
    t1 = TranscriptionVerbose(
        duration=10.0,
        language="en",
        text="Hello",
        words=[TranscriptionWord(word="Hello", start=0.0, end=1.0)],
        segments=[],
        usage=None,
    )
    t2 = TranscriptionVerbose(
        duration=5.0,
        language="en",
        text="World",
        words=[TranscriptionWord(word="World", start=0.0, end=1.0)],
        segments=[],
        usage=None,
    )

    result = template.convert_to_absolute_timing([t1, t2])

    assert len(result) == 2
    # First transcription remains same
    assert result[0].words[0].start == 0.0
    # Second transcription shifted by first duration (10.0)
    assert result[1].words[0].start == 10.0
    assert result[1].words[0].end == 11.0


def test_merge_transcriptions(template):
    t1 = TranscriptionVerbose(
        duration=10.0,
        language="en",
        text="Hello",
        words=[TranscriptionWord(word="Hello", start=0.0, end=1.0)],
        segments=[],
        usage=None,
    )
    t2 = TranscriptionVerbose(
        duration=5.0,
        language="en",
        text="World",
        words=[TranscriptionWord(word="World", start=11.0, end=12.0)],
        segments=[],
        usage=None,
    )

    merged = template.merge_transcriptions([t1, t2])

    assert merged.duration == 15.0
    assert merged.text == "Hello World"
    assert len(merged.words) == 2


def test_transcription_to_ass(template):
    style = SubtitleStyle(max_chars_per_line=50, break_characters=".")
    transcription = TranscriptionVerbose(
        duration=5.0,
        language="en",
        text="Hello world",
        words=[
            TranscriptionWord(word="Hello", start=0.0, end=1.0),
            TranscriptionWord(word="world", start=1.0, end=2.0),
        ],
        segments=[],
        usage=None,
    )

    ass_obj = template.transcription_to_ass(transcription, style)
    assert "[Script Info]" in ass_obj.data
    assert "Hello world" in ass_obj.data


def test_extract_media_timings(template):
    # Setup Reel with Blocks
    # Block 1: Dialogue with Image
    trigger = Trigger(start_word_index=0, end_word_index=0)
    media = ImageMedia(type="image", keywords="test", trigger=trigger)
    block1 = Block(type="dialogue", avatar="a", text="test", media=media)

    # Block 2: Dialogue without media
    block2 = Block(type="dialogue", avatar="b", text="no media", media=None)

    # Subtitles for Block 1
    words1 = [TranscriptionWord(word="test", start=1.0, end=2.0)]
    sub1 = TranscriptionVerbose(
        duration=5.0,
        language="en",
        text="test",
        words=words1,
        segments=[],
        usage=None,
    )

    # Subtitles for Block 2
    words2 = [
        TranscriptionWord(word="no", start=6.0, end=6.5),
        TranscriptionWord(word="media", start=6.5, end=7.0),
    ]
    sub2 = TranscriptionVerbose(
        duration=5.0,
        language="en",
        text="no media",
        words=words2,
        segments=[],
        usage=None,
    )

    images = [MockImageResult("/path/to/img.png")]

    timings = template.extract_media_timings(
        blocks=[block1, block2],
        absolute_subtitles=[sub1, sub2],
        images=images,
        latex=[],
    )

    assert len(timings) == 1
    assert timings[0].filepath == "/path/to/img.png"
    assert timings[0].start_time == 1.0
    assert timings[0].end_time == 2.0
