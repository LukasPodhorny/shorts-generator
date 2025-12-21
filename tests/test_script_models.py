import pytest
from aishorts.modules.script.script import (
    ReelSeries,
    Reel,
    Block,
    ImageMedia,
    LatexMedia,
    Trigger,
)


def test_trigger_model():
    t = Trigger(start_word_index=0, end_word_index=5)
    assert t.start_word_index == 0
    assert t.end_word_index == 5


def test_block_with_image_media():
    trigger = Trigger(start_word_index=0, end_word_index=5)
    media = ImageMedia(type="image", keywords="cat", trigger=trigger)
    block = Block(type="dialogue", avatar="bob", text="hello", media=media)

    assert block.media.type == "image"
    assert block.media.keywords == "cat"
    assert block.media.trigger.start_word_index == 0


def test_block_with_latex_media():
    trigger = Trigger(start_word_index=10, end_word_index=15)
    media = LatexMedia(type="latex", code="E=mc^2", trigger=trigger)
    block = Block(type="dialogue", avatar="alice", text="physics", media=media)

    assert block.media.type == "latex"
    assert block.media.code == "E=mc^2"


def test_reel_series_structure():
    block = Block(type="dialogue", avatar="bob", text="hello")
    reel = Reel(title="Chapter 1", description="Intro", blocks=[block])
    series = ReelSeries(topic="Science", reels=[reel])

    assert series.topic == "Science"
    assert len(series.reels) == 1
    assert series.reels[0].title == "Chapter 1"
    assert len(series.reels[0].blocks) == 1
