"""Offline contract and real-render checks for the formal video pipeline."""

import asyncio
import io
import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from PIL import Image
from pydantic import ValidationError
from redis.exceptions import RedisError

from aishorts import Avatar, FFmpegConfig, ImagesConfig, ScriptConfig, ShortsConfig, ShortsGenerator, SlidesConfig, StockVideoConfig, VideoTemplate
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.modules.image.image_providers import RunPodAI, Unsplash
from aishorts.modules.script.script import AssetType, DialogueBlock, ImageMedia, LatexMedia, ManimMedia, Reel, ReelSeries, SlideMedia, StockVideoMedia, Trigger
from aishorts.modules.script.script_generator import MathLessonSeries, ScriptGenerator
from aishorts.modules.manim.manim_generator import ManimGenerator
from aishorts.modules.slides.renderer import SlideOverflowError, render_slide
from aishorts.modules.slides.slide_generator import SlideGenerator
from aishorts.modules.slides.slide_providers import ModalSlides
from aishorts.modules.slides.style import SlideRenderConfig
from aishorts.modules.stock_video.stock_video_generator import StockVideoGenerator
from aishorts.modules.stock_video.stock_video_providers import AutoStockVideo, LibraryStockVideo, PexelsStockVideo, PixabayStockVideo
from aishorts.modules.video_edit.video_edit import TemplateConfig
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.video_generator import VideoGenerator


def slide(layout="title", **kwargs):
    values = dict(type="slide", layout=layout, title="How knowledge grows",
                  subtitle="Observe, explain, and test.", trigger=Trigger(start_word_index=0, end_word_index=5))
    if layout in {"bullets", "process", "comparison", "timeline", "cycle"}:
        values["items"] = [{"heading": "Observation", "body": "Notice a pattern."},
                           {"heading": "Test", "body": "Check your explanation."}]
    if layout == "cycle":
        values["items"].append({"heading": "Revise", "body": "Try again."})
    if layout == "chart":
        values.update(chart=[{"label": "Before", "value": -5}, {"label": "After", "value": 12}],
                      unit="points", source="Illustrative example")
    if layout == "donut":
        values.update(chart=[{"label": "Soaks in", "value": 50}, {"label": "Runs off", "value": 30},
                             {"label": "Evaporates", "value": 20}], source="Illustrative example")
    if layout == "proportion":
        values.update(chart=[{"label": "Soaks in", "value": 50}, {"label": "Runs off", "value": 30},
                             {"label": "Evaporates", "value": 20}], source="Illustrative example")
    if layout == "line_chart":
        values.update(chart=[{"label": "2020", "x": 2020, "value": 12},
                             {"label": "2022", "x": 2022, "value": 15},
                             {"label": "2025", "x": 2025, "value": 9}],
                      unit="cm", x_unit="year", source="Illustrative example")
    if layout == "metrics":
        values.update(items=[{"heading": "50%", "body": "Soaks in"}, {"heading": "30%", "body": "Runs off"},
                             {"heading": "20%", "body": "Evaporates"}], source="Illustrative example")
    values.update(kwargs)
    return SlideMedia(**values)


def reel():
    return Reel(title="Learning", description="A concise lesson.", blocks=[DialogueBlock(
        type="dialogue", avatar="Narrator", text="Observe a pattern and test it.", media=[slide()],
    )])


def stock_reel():
    return Reel(title="Learning", description="A concise explanation.", blocks=[DialogueBlock(
        type="dialogue", avatar="Narrator", text="Observe a pattern and test it.",
        media=[StockVideoMedia(type="stock_video", keywords="forest canopy",
                               trigger=Trigger(start_word_index=0, end_word_index=5))],
    )])


def stock_validator():
    with patch("aishorts.modules.script.script_generator.LLMProvider.get", return_value=lambda **kw: SimpleNamespace()):
        return ScriptGenerator(base_instructions="voiceover", avatars=[SimpleNamespace(name="Narrator", instructions="Calm")],
                               generate_slides=False, generate_stock_video=True, require_stock_video=True,
                               generate_image=False, generate_latex=False)


def validator(mode="lecture", stock=True, manim=False):
    with patch("aishorts.modules.script.script_generator.LLMProvider.get", return_value=lambda **kw: SimpleNamespace()):
        template = EditTemplate.get(mode)(TemplateConfig())
        return ScriptGenerator(base_instructions="formal", avatars=[SimpleNamespace(name="Narrator", instructions="Calm")],
                               generate_slides=True, generate_stock_video=stock, generate_image=False,
                               generate_latex=False, generate_manim=manim,
                               slide_render_config=template.render_config)


@pytest.mark.parametrize("mode", ["lecture", "documentary", "briefing", "math"])
@pytest.mark.parametrize("layout", ["title", "bullets", "process", "comparison", "chart", "quote",
                                    "metrics", "donut", "timeline", "spotlight", "line_chart", "proportion", "cycle"])
@pytest.mark.parametrize("has_visual", [False, True])
def test_all_layouts_render_readably(mode, layout, has_visual, tmp_path):
    template = EditTemplate.get(mode)(TemplateConfig())
    config = template.render_config.model_copy(update={"has_visual": has_visual})
    path = tmp_path / "slide.png"
    render_slide(slide(layout, title="Příčina a následek: měření a ověření"), config, path)
    with Image.open(path) as image:
        assert image.size == (template.width, template.height)
        assert image.getbbox() is not None


def test_stock_story_uses_only_voice_subtitles_and_full_frame_footage():
    template = EditTemplate.get("stock_story")
    assert (template.width, template.height) == (1920, 1080)
    assert set(template.resolve_required_assets(None)) == {
        AssetType.SCRIPT, AssetType.VOICE, AssetType.SUBTITLES, AssetType.STOCK_VIDEO,
    }
    assert template.tag_assets == {}


def test_math_template_uses_voice_slides_and_enabled_manim():
    template = EditTemplate.get("math")
    assert template.mode == "math"
    assert template.resolve_required_assets(None) == [
        AssetType.SCRIPT, AssetType.VOICE, AssetType.SUBTITLES,
        AssetType.SLIDES, AssetType.LATEX, AssetType.MANIM,
    ]
    assert AssetType.MANIM not in template.resolve_required_assets([])


def test_math_script_preserves_the_animation_window_after_title_insertion():
    sample = reel()
    animation = ManimMedia(type="manim", prompt="Move a point along a number line.",
                           trigger=Trigger(start_word_index=2, end_word_index=4))
    sample.blocks[0].media.append(animation)
    generator = validator(mode="math", stock=False, manim=True)
    generator.validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)
    assert sample.blocks[0].text.startswith("How knowledge grows.")
    assert animation.trigger == Trigger(start_word_index=5, end_word_index=7)
    generator.validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)
    assert animation.trigger == Trigger(start_word_index=5, end_word_index=7)
    with pytest.raises(ValueError, match="at least one animation"):
        generator.validate_script(ReelSeries(topic="Learning", reels=[reel()]), 1)


def math_storyboard(layouts, animated_scenes):
    blocks = []
    for index, layout in enumerate(layouts):
        block = DialogueBlock(type="dialogue", avatar="Narrator",
                              text="Use the diagram to explain this step of the calculation.",
                              media=[slide(layout, title=f"Step {index + 1}")])
        if index in animated_scenes:
            block.media.append(ManimMedia(type="manim", prompt="Show the changing quantity.",
                                          trigger=Trigger(start_word_index=2, end_word_index=8)))
        blocks.append(block)
    return ReelSeries(topic="Learning", reels=[Reel(title="Learning", blocks=blocks)])


def test_math_storyboard_rejects_sparse_animation_and_repeated_lists():
    sample = math_storyboard(["title"] * 10, {3, 7})
    with pytest.raises(ValueError, match="at least 4 Manim scenes"):
        validator(mode="math", stock=False, manim=True).validate_script(sample, 1)
    sample = math_storyboard(["title"] + ["bullets"] * 8 + ["title"], set())
    with pytest.raises(ValueError, match="consecutive scenes"):
        validator(mode="math", stock=False, manim=False).validate_script(sample, 1)


def test_math_storyboard_requires_visual_variety_after_animation():
    layouts = ["title", "bullets", "comparison", "title", "bullets",
               "title", "process", "title", "comparison", "title"]
    sample = math_storyboard(layouts, {1, 3, 5, 7})
    recap = sample.reels[0].blocks[1].media[0]
    recap.subtitle = ""
    recap.items[-1].heading = "The height is 3 units"
    recap.items[-1].body = "Check it in the original triangle."
    validator(mode="math", stock=False, manim=True).validate_script(sample, 1)
    assert recap.layout == "title"
    assert recap.subtitle == "The height is 3 units: Check it in the original triangle."
    assert recap.items == []

    validator(mode="math", stock=False, manim=True).validate_script(sample, 1)

    sample.reels[0].blocks[2].media[0] = slide("bullets", title="Step 3")
    sample.reels[0].blocks[8].media[0] = slide("bullets", title="Step 9")
    with pytest.raises(ValueError, match="list-style slides"):
        validator(mode="math", stock=False, manim=True).validate_script(sample, 1)


def test_math_animations_are_spread_through_the_lesson():
    sample = math_storyboard(["title"] * 10, {6, 7, 8, 9})
    with pytest.raises(ValueError, match="Spread Math animations"):
        validator(mode="math", stock=False, manim=True).validate_script(sample, 1)


def test_math_narration_does_not_name_the_rendering_tool():
    sample = math_storyboard(["title"] * 10, {1, 3, 5, 7})
    sample.reels[0].blocks[1].text = "This Manim animation shows how the angle changes."
    with pytest.raises(ValueError, match="Do not mention Manim"):
        validator(mode="math", stock=False, manim=True).validate_script(sample, 1)


def test_math_response_schema_requires_a_slide_in_every_scene():
    payload = {"topic": "Slope", "reels": [{"title": "A changing slope", "blocks": [{
        "avatar": "Narrator", "text": "The point moves along the curve.",
        "slide": {"type": "slide", "layout": "title", "title": "A changing slope", "subtitle": "Slope depends on position."},
        "visual": {"type": "manim", "prompt": "Move a point along the curve.",
                   "trigger": {"start_word_index": 1, "end_word_index": 5}},
    }]}]}
    incomplete = json.loads(json.dumps(payload))
    del incomplete["reels"][0]["blocks"][0]["slide"]
    with pytest.raises(ValidationError, match="slide"):
        MathLessonSeries.model_validate(incomplete)

    generator = validator(mode="math", stock=False, manim=True)
    generator.llm.generate_structure = AsyncMock(return_value=MathLessonSeries.model_validate(payload))

    async def immediate_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("aishorts.modules.script.script_generator.asyncio.to_thread", new=immediate_thread):
        result = asyncio.run(generator.generate_script(user_input="Explain slope"))

    assert generator.llm.generate_structure.call_args.kwargs["response_schema"] is MathLessonSeries
    assert [media.type for media in result.reels[0].blocks[0].media] == ["slide", "manim"]


@pytest.mark.parametrize(("start", "end", "expected"), [
    (2, 99, (5, 8)),
    (99, 100, (3, 8)),
    (4, 1, (3, 8)),
])
def test_math_script_normalizes_invalid_animation_windows(start, end, expected):
    sample = reel()
    animation = ManimMedia(type="manim", prompt="Move a point along a number line.",
                           trigger=Trigger(start_word_index=start, end_word_index=end))
    sample.blocks[0].media.append(animation)
    generator = validator(mode="math", stock=False, manim=True)

    generator.validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)

    assert animation.trigger == Trigger(start_word_index=expected[0], end_word_index=expected[1])


def test_math_equation_slide_is_validated_with_and_without_its_panel():
    sample = reel()
    sample.blocks[0].media.append(LatexMedia(type="latex", code="x^2", trigger=Trigger(start_word_index=0, end_word_index=5)))
    generator = validator(mode="math", stock=False, manim=False)
    generator.generate_latex = True
    with patch("aishorts.modules.slides.renderer.render_slide") as render:
        generator.validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)
    assert [call.args[1].has_visual for call in render.call_args_list] == [False, True]


def test_math_slide_keeps_full_width_when_manim_is_available(tmp_path):
    sample = reel()
    animation = ManimMedia(type="manim", prompt="Move a point.", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(animation)
    sample.blocks[0].assets.media_map[animation.id] = str(tmp_path / "animation.mp4")
    generator = SlideGenerator(render_config=EditTemplate.get("math")(TemplateConfig()).render_config,
                               upload=False, output_dir=tmp_path / "slides")
    observed = []

    async def render(_slide, config, path):
        observed.append(config.has_visual)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preview")

    generator.provider.render = render
    asyncio.run(generator.populate_reel(sample))
    assert observed == [False]
    assert sample.blocks[0].assets.slide_viewport is None


def test_math_manim_failure_is_fatal_and_success_has_durable_url(tmp_path):
    sample = reel()
    animation = ManimMedia(type="manim", prompt="Move a point.", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(animation)
    with patch("aishorts.modules.manim.manim_generator.ManimProvider.get", return_value=lambda **_: SimpleNamespace()), \
         patch("aishorts.modules.manim.manim_generator.LLMGenerator"):
        generator = ManimGenerator(failure_mode="error", upload=True)
    clip = tmp_path / "animation.mp4"
    clip.write_bytes(b"clip")
    generator.generate = AsyncMock(return_value=SimpleNamespace(media=SimpleNamespace(path=str(clip), url=None)))
    storage = Mock()
    storage.upload_file.return_value = "https://media.example/manim/animation.mp4"

    async def immediate_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("aishorts.utils.r2_handler.CloudflareR2", return_value=storage), \
         patch("aishorts.modules.manim.manim_generator.asyncio.to_thread", new=immediate_thread):
        asyncio.run(generator.populate_reel(sample))
    assert sample.blocks[0].assets.media_map[animation.id] == str(clip)
    assert sample.blocks[0].assets.media_url_map[animation.id] == storage.upload_file.return_value
    generator.generate = AsyncMock(side_effect=RuntimeError("invalid animation"))
    with pytest.raises(RuntimeError, match="invalid animation"):
        asyncio.run(generator.populate_reel(sample))


def test_math_manim_retries_a_clip_too_short_to_explain_the_change(tmp_path):
    clips = []
    for seconds in (4, 10):
        clip = tmp_path / f"animation-{seconds}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        f"color=c=red:s=160x90:r=30:d={seconds}", "-c:v", "libx264",
                        "-preset", "ultrafast", "-y", str(clip)], check=True)
        clips.append(SimpleNamespace(media=SimpleNamespace(path=str(clip))))

    provider = SimpleNamespace(render=AsyncMock(side_effect=clips))
    with patch("aishorts.modules.manim.manim_generator.ManimProvider.get", return_value=lambda **_: provider), \
         patch("aishorts.modules.manim.manim_generator.LLMGenerator") as llm:
        llm.return_value.generate_response = AsyncMock(return_value="from manim import *\nclass GenScene(Scene):\n    pass")
        generator = ManimGenerator(min_duration_seconds=8)
        result = asyncio.run(generator.generate("Show the change."))

    assert result is clips[1]
    assert provider.render.await_count == 2
    assert "too short" in llm.return_value.generate_response.await_args_list[1].kwargs["instructions"]


@pytest.mark.parametrize(("change", "error"), [
    (lambda b: setattr(b, "avatar", "Unknown"), "avatar"),
    (lambda b: b.media.clear(), "exactly one stock clip"),
    (lambda b: b.media.append(slide()), "exactly one stock clip"),
])
def test_stock_story_contract_rejects_non_footage_scenes(change, error):
    sample = stock_reel()
    change(sample.blocks[0])
    with pytest.raises(ValueError, match=error):
        stock_validator().validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)


def test_stock_story_contract_normalizes_clip_to_whole_voiceover():
    sample = stock_reel()
    sample.blocks[0].media[0].trigger = Trigger(start_word_index=9, end_word_index=20)
    generator = stock_validator()
    generator.validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)
    assert sample.blocks[0].media[0].trigger == Trigger(start_word_index=0, end_word_index=5)
    instructions = generator._generate_instructions(1)
    assert "Stock video: REQUIRED" in instructions
    assert "Slides: DISABLED" in instructions


def test_bad_chart_and_comparison_rejected():
    with pytest.raises(ValidationError, match="source"):
        slide("chart", source="")
    with pytest.raises(ValidationError, match="exactly two"):
        slide("comparison", items=[{"heading": "Alone"}])
    with pytest.raises(ValidationError):
        slide("chart", chart=[{"label": "x", "value": float("nan")}, {"label": "y", "value": 1}])
    with pytest.raises(ValidationError, match="positive shares"):
        slide("donut", chart=[{"label": "Before", "value": 0}, {"label": "After", "value": 12}])
    with pytest.raises(ValidationError, match="values, labels, and a source"):
        slide("metrics", source="")
    with pytest.raises(ValidationError, match="chronological milestones"):
        slide("timeline", items=[{"heading": "Only one milestone"}])
    with pytest.raises(ValidationError, match="ordered numeric x"):
        slide("line_chart", chart=[{"label": "first", "x": 5, "value": 2},
                                   {"label": "second", "x": 3, "value": 4}])
    with pytest.raises(ValidationError, match="positive shares"):
        slide("proportion", chart=[{"label": "A", "value": 0}, {"label": "B", "value": 1}])
    with pytest.raises(ValidationError, match="connected stages"):
        slide("cycle", items=[{"heading": "Only one"}])


def test_text_overflow_is_not_silently_clipped():
    from aishorts.modules.slides.renderer import text_box
    from PIL import ImageDraw
    with pytest.raises(SlideOverflowError):
        text_box(ImageDraw.Draw(Image.new("RGB", (100, 100))), "Too much text " * 30,
                 (0, 0, 100, 30), "black")


@pytest.mark.parametrize("change,error", [
    (lambda b: setattr(b, "avatar", "Unknown"), "avatar"),
    (lambda b: b.media.clear(), "exactly one"),
    (lambda b: b.media.append(StockVideoMedia(type="stock_video", keywords="forest", trigger=Trigger(start_word_index=0, end_word_index=5))), "disabled"),
])
def test_script_contract_rejects_invalid_content(change, error):
    sample = reel()
    change(sample.blocks[0])
    with pytest.raises(ValueError, match=error):
        validator(stock=False).validate_script(ReelSeries(topic="Learning", reels=[sample]), 1)


def test_documentary_recovers_from_stock_trigger_beyond_narration():
    sample = reel()
    block = sample.blocks[0]
    block.text = " ".join(["word"] * 22)
    stock = StockVideoMedia(
        type="stock_video", keywords="forest",
        trigger=Trigger(start_word_index=0, end_word_index=30),
    )
    block.media.append(stock)
    generator = validator(mode="documentary")
    generator.llm.generate_structure = AsyncMock(return_value=ReelSeries(topic="Learning", reels=[sample]))

    result = asyncio.run(generator.generate_script(user_input="teach"))

    assert result.reels[0].blocks[0].media[1].trigger == Trigger(start_word_index=0, end_word_index=24)
    generator.llm.generate_structure.assert_awaited_once()


@pytest.mark.parametrize(("spans", "split"), [([(0, 1), (4, 5)], 7), ([(0, 30), (0, 0)], 4)])
def test_two_visuals_normalize_to_contiguous_ranges(spans, split):
    sample = reel()
    clips = [
        StockVideoMedia(type="stock_video", keywords="forest",
                        trigger=Trigger(start_word_index=start, end_word_index=end))
        for start, end in spans
    ]
    sample.blocks[0].media.extend(clips)
    validator(mode="documentary").validate_script(ReelSeries(topic="Learning", reels=[sample]))
    assert [clip.trigger for clip in clips] == [
        Trigger(start_word_index=0, end_word_index=split - 1),
        Trigger(start_word_index=split, end_word_index=8),
    ]


@pytest.mark.parametrize("end", [4, 99])
def test_generated_slide_timing_uses_full_narration_without_retry(end):
    generator = validator(mode="documentary")
    sample = ReelSeries(topic="Learning", reels=[reel()])
    sample.reels[0].blocks[0].media[0].trigger = Trigger(start_word_index=1, end_word_index=end)
    generator.llm.generate_structure = AsyncMock(return_value=sample)

    result = asyncio.run(generator.generate_script(user_input="teach"))

    block = result.reels[0].blocks[0]
    assert block.text == "How knowledge grows. Observe a pattern and test it."
    assert block.media[0].trigger == Trigger(start_word_index=0, end_word_index=8)
    generator.validate_script(result)
    assert block.text == "How knowledge grows. Observe a pattern and test it."
    generator.llm.generate_structure.assert_awaited_once()


def test_script_retries_contract_failure():
    generator = validator()
    bad = ReelSeries(topic="Learning", reels=[reel()])
    bad.reels[0].blocks[0].avatar = "Unknown"
    good = ReelSeries(topic="Learning", reels=[reel()])
    generator.llm.generate_structure = AsyncMock(side_effect=[bad, good])
    assert asyncio.run(generator.generate_script(user_input="teach")) == good
    assert generator.llm.generate_structure.await_count == 2
    assert "failed validation" in generator.llm.generate_structure.call_args.kwargs["instructions"]


def test_math_script_recovers_when_model_bundles_all_slides_into_one_scene():
    generator = validator(mode="math", stock=False, manim=True)
    bad_scripts = []
    for _ in range(2):
        sample = reel()
        sample.blocks[0].media.extend(slide() for _ in range(8))
        bad_scripts.append(ReelSeries(topic="Sequences", reels=[sample]))

    good_reel = reel()
    good_reel.blocks[0].media.append(ManimMedia(
        type="manim", prompt="Show the terms of an arithmetic sequence on a number line.",
        trigger=Trigger(start_word_index=0, end_word_index=4),
    ))
    good = ReelSeries(topic="Sequences", reels=[good_reel])
    generator.llm.generate_structure = AsyncMock(side_effect=[*bad_scripts, good])

    async def immediate_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("aishorts.modules.script.script_generator.asyncio.to_thread", new=immediate_thread):
        result = asyncio.run(generator.generate_script(user_input="Explain sequences and series"))

    assert result == good
    assert generator.llm.generate_structure.await_count == 3
    correction = generator.llm.generate_structure.await_args_list[1].kwargs["instructions"]
    assert "separate dialogue block" in correction


def test_provider_fallback_and_disabled_modules(tmp_path):
    sample = reel()
    sample.blocks[0].media.append(StockVideoMedia(type="stock_video", keywords="forest", trigger=Trigger(start_word_index=0, end_word_index=5)))
    stock = StockVideoGenerator(provider="library", upload=False, output_dir=tmp_path / "stock")
    stock.provider.get_clip = AsyncMock(side_effect=TimeoutError("deadline"))
    asyncio.run(stock.populate_reel(sample))
    assert not sample.blocks[0].assets.media_map
    slides = SlideGenerator(upload=False, output_dir=tmp_path / "slides")
    asyncio.run(slides.populate_reel(sample))
    assert Path(sample.blocks[0].assets.media_map[sample.blocks[0].media[0].id]).is_file()
    strict = StockVideoGenerator(provider="library", upload=False, failure_mode="error")
    strict.provider.get_clip = AsyncMock(side_effect=TimeoutError("deadline"))
    with pytest.raises(TimeoutError):
        asyncio.run(strict.populate_reel(sample))


def test_optional_image_provider_error_keeps_the_slide():
    sample = reel()
    image = ImageMedia(type="image", keywords="An oak tree.", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(image)
    generator = ImageGenerator(provider="unsplash", allow_missing=True)
    generator.image_gen.populate_reel = AsyncMock(side_effect=TimeoutError("deadline"))
    with patch("aishorts.modules.image.image_providers.RunPodAI") as fallback:
        asyncio.run(generator.populate_reel(sample))
    assert not sample.blocks[0].assets.media_map
    fallback.assert_not_called()


def test_documentary_illustrations_use_editorial_direction():
    config = ShortsConfig(
        avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
        video_template=VideoTemplate(edit_template="documentary", template_config={}),
        enabled_tags=[],
        ffmpeg_config=FFmpegConfig(provider="local_ffmpeg"),
        slides_config=SlidesConfig(provider_config={"upload": False}),
        images_config=ImagesConfig(provider="runpod_ai"),
    )
    with patch("aishorts.shorts_generator.ScriptGenerator"), patch("aishorts.shorts_generator.SubtitleGenerator"), \
         patch("aishorts.modules.latex.latex_providers.CloudflareR2"):
        generator = ShortsGenerator(config)
    provider = generator.image_gen.image_gen
    assert isinstance(provider, RunPodAI)
    sample = reel()
    image = ImageMedia(type="image", keywords="Mist rising from a lake.", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(image)
    with patch.object(provider, "get_images", new_callable=AsyncMock, return_value=[None]) as render:
        asyncio.run(generator.image_gen.populate_reel(sample))
    prompt = render.call_args.kwargs["prompts"][0]
    assert prompt.startswith(image.keywords)
    assert "Editorial illustration" in prompt
    assert not sample.blocks[0].assets.media_map


def test_pexels_selects_orientation_and_caps_resolution():
    data = {"videos": [{"duration": 12, "video_files": [
        {"width": 3840, "height": 2160, "file_type": "video/mp4", "link": "4k"},
        {"width": 720, "height": 1280, "file_type": "video/mp4", "link": "portrait"},
        {"width": 1280, "height": 720, "file_type": "video/mp4", "link": "landscape"},
    ]}]}
    assert PexelsStockVideo.select_file(data, "landscape")[1]["link"] == "landscape"
    assert PexelsStockVideo.select_file(data, "portrait")[1]["link"] == "portrait"
    for url in ["http://videos.pexels.com/a", "https://localhost/a", "https://videos.pexels.com.evil.test/a", "https://user:pass@videos.pexels.com/a"]:
        with pytest.raises(ValueError):
            PexelsStockVideo._safe_download_url(url)


def test_library_rejects_path_escape(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"path": "../private.mp4", "keywords": ["forest"], "creator": "Owner", "license": "Owned"}]))
    provider = LibraryStockVideo(manifest_path=manifest)
    with pytest.raises(ValueError, match="inside"):
        asyncio.run(provider.get_clip("forest", "landscape", tmp_path / "output"))


class HTTPResponse:
    """Small streaming response double; exercises provider HTTP contracts offline."""

    def __init__(self, *, data=None, chunks=(), status=200, headers=None,
                 content_length=None, content_type="image/png"):
        self.data, self.chunks, self.status = data, chunks, status
        self.headers = headers or {}
        self.content_length, self.content_type = content_length, content_type
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self.data

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


def http_session(**methods):
    session = HTTPResponse()
    for method, responses in methods.items():
        setattr(session, method, Mock(side_effect=responses))
    return session


def pexels_result(url="https://videos.pexels.com/clip.mp4"):
    return {"videos": [{"duration": 12, "url": "https://www.pexels.com/video/123/",
                        "user": {"name": "Creator"}, "video_files": [
        {"width": 1280, "height": 720, "file_type": "video/mp4", "link": url},
    ]}]}


def pixabay_result(url="https://cdn.pixabay.com/video/clip.mp4"):
    return {"hits": [{"id": 123, "duration": 12, "pageURL": "https://pixabay.com/videos/id-123/",
                      "user": "Creator", "videos": {
        "large": {"width": 3840, "height": 2160, "size": 20, "url": "https://cdn.pixabay.com/video/4k.mp4"},
        "medium": {"width": 1280, "height": 720, "size": 12, "url": url},
        "small": {"width": 720, "height": 1280, "size": 12,
                  "url": "https://cdn.pixabay.com/video/portrait.mp4"},
    }}]}


def pixabay_cache():
    values = {}
    cache = Mock()
    cache.get.side_effect = values.get

    def save(key, seconds, value):
        values[key] = value
        return True

    cache.setex.side_effect = save
    return cache


def test_pixabay_selects_bounded_hd_in_requested_orientation(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("PIXABAY_API_KEY", "test-key")
    provider = AutoStockVideo(cache=pixabay_cache()).provider
    assert isinstance(provider, PixabayStockVideo)
    assert provider.select_file(pixabay_result(), "landscape")[1]["url"].endswith("clip.mp4")
    assert provider.select_file(pixabay_result(), "portrait")[1]["url"].endswith("portrait.mp4")
    assert provider.select_file(pixabay_result(), "landscape")[1]["size"] <= provider.max_bytes
    for url in ["http://cdn.pixabay.com/video/a.mp4", "https://localhost/video/a.mp4",
                "https://cdn.pixabay.com.evil.test/video/a.mp4", "https://cdn.pixabay.com/photo/a.mp4",
                "https://user:pass@cdn.pixabay.com/video/a.mp4"]:
        with pytest.raises(ValueError):
            provider._safe_download_url(url)


def test_pixabay_caches_search_for_24_hours_and_keeps_key_off_download(tmp_path):
    cache = pixabay_cache()
    session = http_session(get=[HTTPResponse(status=429), HTTPResponse(data=pixabay_result()),
                                HTTPResponse(chunks=[b"video bytes"])])
    provider = PixabayStockVideo(api_key="secret-key", cache=cache)
    with patch("aiohttp.ClientSession", return_value=session), patch("asyncio.sleep", new_callable=AsyncMock) as sleep, \
         patch("aishorts.modules.stock_video.stock_video_providers.probe_clip", return_value={}):
        clip = asyncio.run(provider.get_clip("clouds", "landscape", tmp_path))
        cached = asyncio.run(provider._search(session, "clouds", "landscape"))
    assert cached == pixabay_result()
    assert session.get.call_count == 3
    assert sleep.await_count == 1
    assert session.get.call_args_list[0].kwargs["params"]["key"] == "secret-key"
    assert session.get.call_args_list[0].kwargs["params"]["safesearch"] == "true"
    assert session.get.call_args_list[0].kwargs["params"]["per_page"] == 100
    assert "key" not in session.get.call_args_list[2].kwargs
    assert "secret-key" not in repr(session.get.call_args_list[2])
    assert cache.setex.call_args.args[1] == 24 * 60 * 60
    assert Path(clip.path).read_bytes() == b"video bytes"
    assert (clip.attribution.provider, clip.attribution.creator) == ("Pixabay", "Creator")
    assert clip.attribution.source_url == "https://pixabay.com/videos/id-123/"


def test_pixabay_cache_failure_prevents_uncached_search(tmp_path):
    cache = Mock()
    cache.get.side_effect = RedisError("unavailable")
    session = http_session(get=[])
    provider = PixabayStockVideo(api_key="secret-key", cache=cache)
    with patch("aiohttp.ClientSession", return_value=session), pytest.raises(RuntimeError, match="cache is unavailable") as error:
        asyncio.run(provider.get_clip("clouds", "landscape", tmp_path))
    assert "secret-key" not in str(error.value)
    session.get.assert_not_called()


def test_pixabay_failed_download_removes_partial_file(tmp_path):
    session = http_session(get=[HTTPResponse(data=pixabay_result()),
                                HTTPResponse(status=302, headers={"Location": "https://localhost/private.mp4"})])
    provider = PixabayStockVideo(api_key="secret-key", cache=pixabay_cache())
    with patch("aiohttp.ClientSession", return_value=session), pytest.raises(ValueError, match="unsupported download host"):
        asyncio.run(provider.get_clip("clouds", "landscape", tmp_path))
    assert not list(tmp_path.iterdir())


def test_stock_story_uses_distinct_pixabay_clips_across_scenes(tmp_path):
    data = {"hits": [{
        "id": clip_id, "duration": 12, "pageURL": f"https://pixabay.com/videos/id-{clip_id}/",
        "user": "Creator", "videos": {"medium": {
            "width": 1280, "height": 720, "size": 10,
            "url": f"https://cdn.pixabay.com/video/{clip_id}.mp4",
        }},
    } for clip_id in range(100, 105)]}
    cache = Mock()
    cache.get.return_value = json.dumps(data)
    session = http_session(get=[HTTPResponse(chunks=[b"video bytes"]) for _ in range(5)])
    sample = stock_reel()
    for _ in range(4):
        sample.blocks.extend(stock_reel().blocks)
    for index, block in enumerate(sample.blocks):
        block.media[0].keywords = "ants" if index % 2 else "ant colony"
    generator = StockVideoGenerator(provider="pixabay", api_key="test-key", cache=cache,
                                    upload=False, failure_mode="error", output_dir=tmp_path)
    with patch("aiohttp.ClientSession", return_value=session), \
         patch("aishorts.modules.stock_video.stock_video_providers.probe_clip", return_value={}):
        asyncio.run(generator.populate_reel(sample))
    sources = [block.assets.media_attributions[block.media[0].id].source_url for block in sample.blocks]
    assert len(set(sources)) == len(sample.blocks)
    assert session.get.call_count == 5


def test_stock_story_stops_when_only_used_pixabay_clip_remains(tmp_path):
    cache = Mock()
    cache.get.return_value = json.dumps(pixabay_result())
    session = http_session(get=[HTTPResponse(chunks=[b"video bytes"])])
    sample = stock_reel()
    sample.blocks.extend(stock_reel().blocks)
    generator = StockVideoGenerator(provider="pixabay", api_key="test-key", cache=cache,
                                    upload=False, failure_mode="error", output_dir=tmp_path)
    with patch("aiohttp.ClientSession", return_value=session), \
         patch("aishorts.modules.stock_video.stock_video_providers.probe_clip", return_value={}), \
         pytest.raises(LookupError, match="No unused stock footage"):
        asyncio.run(generator.populate_reel(sample))
    assert session.get.call_count == 1


def test_unsplash_preserves_credit_and_tracks_selected_photo(tmp_path):
    sample = reel()
    photo = ImageMedia(type="image", keywords="A forest.", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(photo)
    track_url = "https://api.unsplash.com/photos/photo-id/download"
    search = http_session(get=[HTTPResponse(data={"results": [{
        "urls": {"raw": "https://images.unsplash.com/photo-example"},
        "user": {"name": "Photographer", "username": "photographer"},
        "links": {"download_location": track_url},
    }]})])
    tracking = http_session(get=[HTTPResponse()])
    provider = Unsplash(api_key="test-key")
    provider.OUTPUT_DIR = str(tmp_path)
    with patch("aiohttp.ClientSession", side_effect=[search, tracking]), \
         patch("aishorts.modules.image.image_providers.download_from_url", new_callable=AsyncMock) as download:
        asyncio.run(provider.populate_reel(sample, 1280, 960))

    tracking.get.assert_called_once_with(track_url, headers={"Authorization": "Client-ID test-key"}, allow_redirects=False)
    assert "client_id" not in search.get.call_args.kwargs["params"]
    assert download.await_args.args[0].startswith("https://images.unsplash.com/")
    assert "test-key" not in repr(download.await_args)
    credit = sample.blocks[0].assets.media_attributions[photo.id]
    assert credit.creator == "Photographer"
    assert credit.source_url.startswith("https://unsplash.com/@photographer?")


@pytest.mark.parametrize("first_available", [False, True])
def test_composed_photo_panel_has_no_gap_at_changeover(tmp_path, first_available):
    sample = reel()
    add_audio(sample, tmp_path / "narration.wav", duration=1.0)
    block = sample.blocks[0]
    for index, color in enumerate(("red", "blue")):
        media = ImageMedia(type="image", keywords=f"{color} photo", trigger=Trigger(
            start_word_index=index * 3, end_word_index=index * 3 + 2,
        ))
        block.media.append(media)
        if first_available or index == 1:
            path = tmp_path / f"{color}.jpg"
            Image.new("RGB", (640, 480), color).save(path)
            block.assets.media_map[media.id] = str(path)
    render_config = EditTemplate.get("briefing")(TemplateConfig()).render_config
    slides = SlideGenerator(render_config=render_config, upload=False, output_dir=tmp_path)
    asyncio.run(slides.populate_reel(sample))
    # The compositor uses the stored photo viewport when loading a checkpoint.
    sample = Reel.model_validate_json(sample.model_dump_json())
    video = VideoGenerator(VideoTemplate(edit_template="briefing", template_config={}),
                           provider="local_ffmpeg", encoder_preset="ultrafast", render_timeout=30)
    video.render.video_codec = "libx264"
    video.render.OUTPUT_DIR = str(tmp_path)
    result = asyncio.run(video.compose(sample))
    x, y, w, h = sample.blocks[0].assets.slide_viewport

    def color_at(t):
        return subprocess.check_output([
            "ffmpeg", "-v", "error", "-ss", str(t), "-i", result.filepath, "-frames:v", "1",
            "-vf", f"crop=2:2:{x + w // 2}:{y + h // 2}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ])[:3]

    for time, expected_channel in ((0, 0 if first_available else 2), (0.5, 2), (0.9, 2)):
        assert color_at(time)[expected_channel] > 210


def test_pexels_retries_and_keeps_credentials_off_downloads(tmp_path):
    session = http_session(get=[HTTPResponse(status=429), HTTPResponse(data=pexels_result()),
                                HTTPResponse(chunks=[b"video bytes"])])
    provider = PexelsStockVideo(api_key="test-key")
    with patch("aiohttp.ClientSession", return_value=session), patch("asyncio.sleep", new_callable=AsyncMock) as sleep, \
         patch("aishorts.modules.stock_video.stock_video_providers.probe_clip", return_value={}):
        clip = asyncio.run(provider.get_clip("clouds", "landscape", tmp_path))
    sleep.assert_awaited_once_with(1)
    calls = session.get.call_args_list
    assert calls[0].kwargs["headers"] == {"Authorization": "test-key"}
    assert calls[1].kwargs["params"]["orientation"] == "landscape"
    assert "headers" not in calls[2].kwargs
    assert all(call.kwargs["allow_redirects"] is False for call in calls)
    assert Path(clip.path).read_bytes() == b"video bytes"
    assert clip.attribution.creator == "Creator"
    assert clip.attribution.source_url == "https://www.pexels.com/video/123/"


@pytest.mark.parametrize("response,error", [
    (HTTPResponse(chunks=[b"12345", b"67890"]), "size limit"),
    (HTTPResponse(content_length=100), "size limit"),
    (HTTPResponse(status=302, headers={"Location": "https://localhost/private"}), "unsupported download host"),
])
def test_pexels_failed_download_removes_partial_files(response, error, tmp_path):
    session = http_session(get=[HTTPResponse(data=pexels_result()), response])
    provider = PexelsStockVideo(api_key="test-key", max_bytes=8)
    with patch("aiohttp.ClientSession", return_value=session), pytest.raises(ValueError, match=error):
        asyncio.run(provider.get_clip("clouds", "landscape", tmp_path))
    assert not list(tmp_path.iterdir())
    assert session.get.call_count == 2


def test_pexels_rejects_corrupt_video_after_download(tmp_path):
    session = http_session(get=[HTTPResponse(data=pexels_result()), HTTPResponse(chunks=[b"corrupt"])])
    with patch("aiohttp.ClientSession", return_value=session), \
         patch("aishorts.modules.stock_video.stock_video_providers.probe_clip", side_effect=ValueError("unplayable")), \
         pytest.raises(ValueError, match="unplayable"):
        asyncio.run(PexelsStockVideo(api_key="test-key").get_clip("clouds", "landscape", tmp_path))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("image_format,size,error", [
    ("PNG", (1920, 1080), None),
    ("JPEG", (1920, 1080), "non-PNG image"),
    ("PNG", (100, 100), "incorrect dimensions"),
])
def test_modal_slides_validates_image_before_atomic_write(image_format, size, error, tmp_path):
    data = io.BytesIO()
    Image.new("RGB", size).save(data, image_format)
    session = http_session(post=[HTTPResponse(chunks=[data.getvalue()])])
    provider = ModalSlides(endpoint_url="https://example.modal.run/", api_key="test-key")
    output = tmp_path / "slide.png"
    output.write_bytes(b"previous image")
    with patch("aiohttp.ClientSession", return_value=session):
        if error:
            with pytest.raises(ValueError, match=error):
                asyncio.run(provider.render(slide(), SlideRenderConfig(), output))
            assert output.read_bytes() == b"previous image"
        else:
            assert asyncio.run(provider.render(slide(), SlideRenderConfig(), output)) == str(output)
            with Image.open(output) as rendered:
                assert rendered.format == "PNG"
                assert rendered.size == size
    assert list(tmp_path.iterdir()) == [output]
    assert session.post.call_args.kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert session.post.call_args.kwargs["allow_redirects"] is False


def add_audio(sample, path, duration=0.6):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\x00\x00" * int(duration * 24000))
    for block in sample.blocks:
        block.assets.voice_filepath = str(path)
        words = block.text.split()
        block.assets.subtitles = TranscriptionVerbose(duration=duration, language="en", text=block.text,
            words=[TranscriptionWord(word=w, start=i * duration / len(words), end=(i + 1) * duration / len(words)) for i, w in enumerate(words)])


@pytest.mark.parametrize("mode", ["lecture", "documentary", "briefing"])
@pytest.mark.parametrize("clip_duration", [0.2, 14])
def test_actual_ffmpeg_render_with_mixed_scenes_and_checkpoint(mode, clip_duration, tmp_path):
    sample = reel()
    second = reel().blocks[0]
    sample.blocks.append(second)
    duration = 3.5 if clip_duration > 1 else 0.6
    add_audio(sample, tmp_path / "narration.wav", duration)
    # A short, silent clip exercises tpad, cropping, and a stock input with no audio.
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s=640x480:d={clip_duration}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(clip)], check=True)
    media = StockVideoMedia(type="stock_video", keywords="red", trigger=Trigger(start_word_index=0, end_word_index=5))
    sample.blocks[0].media.append(media)
    sample.blocks[0].assets.media_map[media.id] = str(clip)
    template = EditTemplate.get(mode)(TemplateConfig())
    generator = SlideGenerator(render_config=template.render_config, upload=False, output_dir=tmp_path / "slides")
    asyncio.run(generator.populate_reel(sample))
    sample = Reel.model_validate_json(sample.model_dump_json())
    video = VideoGenerator(VideoTemplate(edit_template=mode, template_config={}), provider="local_ffmpeg", encoder_preset="ultrafast", render_timeout=30)
    video.render.video_codec = "libx264"
    video.render.OUTPUT_DIR = str(tmp_path)
    result = asyncio.run(video.compose(sample))
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", result.filepath]))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (template.width, template.height)
    assert stream["pix_fmt"] == "yuv420p"
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert abs(float(probe["format"]["duration"]) - duration * 2) < 0.08


def test_math_animation_starts_without_a_slide_flash_and_holds_before_the_next_slide(tmp_path):
    sample = reel()
    sample.blocks.append(reel().blocks[0])
    sample.blocks[0].media.append(ManimMedia(type="manim", prompt="Show a moving point.",
        trigger=Trigger(start_word_index=2, end_word_index=4)))
    validator(mode="math", stock=False, manim=True).validate_script(
        ReelSeries(topic="Learning", reels=[sample]), 1)
    add_audio(sample, tmp_path / "narration.wav", duration=1.2)
    clip = tmp_path / "animation.mp4"
    subprocess.run(["ffmpeg", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=320x180:r=30:d=0.8",
                    "-f", "lavfi", "-i", "color=c=yellow:s=320x180:r=30:d=0.8",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(clip)], check=True)
    manim = sample.blocks[0].media[1]
    sample.blocks[0].assets.media_map[manim.id] = str(clip)
    for block, color in zip(sample.blocks, ("green", "blue")):
        slide_path = tmp_path / f"{color}.png"
        Image.new("RGB", (320, 180), color).save(slide_path)
        block.assets.media_map[block.media[0].id] = str(slide_path)
    sample = Reel.model_validate_json(sample.model_dump_json())
    video = VideoGenerator(VideoTemplate(edit_template="math", template_config={}),
                           provider="local_ffmpeg", encoder_preset="ultrafast", render_timeout=30)
    video.edit.width, video.edit.height = 320, 180
    video.render.video_codec = "libx264"
    video.render.OUTPUT_DIR = str(tmp_path)
    result = asyncio.run(video.compose(sample))
    for at, expected in ((0.05, "red"), (1.7, "yellow"), (4.8, "yellow"),
                         (5.7, "green"), (8.5, "blue"), (11.0, "blue")):
        pixel = subprocess.check_output([
            "ffmpeg", "-v", "error", "-ss", str(at), "-i", result.filepath,
            "-frames:v", "1", "-vf", "crop=2:2:20:20", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ])[:3]
        channels = {"red": (True, False, False), "yellow": (True, True, False),
                    "green": (False, True, False), "blue": (False, False, True)}
        assert tuple(channel > 100 for channel in pixel) == channels[expected]
    rendered_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", result.filepath,
    ]))
    assert rendered_duration >= 11.3


def test_stock_story_renders_only_full_frame_footage_and_voiceover(tmp_path):
    sample = stock_reel()
    sample.blocks.append(stock_reel().blocks[0])
    add_audio(sample, tmp_path / "voice.wav", 0.6)
    for block, color, size in zip(sample.blocks, ("red", "blue"), ("640x480", "640x360")):
        stock = tmp_path / f"{color}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d=0.2",
                        "-c:v", "libx264", "-y", str(stock)], check=True)
        block.assets.media_map[block.media[0].id] = str(stock)
        block.assets.lipsync_filepath = str(tmp_path / "unused-avatar.mp4")
        block.assets.staticface_filepath = str(tmp_path / "unused-avatar.png")
    sample = Reel.model_validate_json(sample.model_dump_json())
    template = EditTemplate.get("stock_story")(TemplateConfig())
    command = template.compose(sample)
    assert len(command.inputs) == 4  # Two clips and two narration inputs; no avatar or slide.
    assert all("avatar" not in str(value) for value in command.inputs)
    assert "overlay" not in command.args[1]
    video = VideoGenerator(VideoTemplate(edit_template="stock_story", template_config={}),
                           provider="local_ffmpeg", encoder_preset="ultrafast", render_timeout=30)
    video.render.video_codec = "libx264"
    video.render.OUTPUT_DIR = str(tmp_path)
    result = asyncio.run(video.compose(sample))
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", result.filepath]))
    assert abs(float(probe["format"]["duration"]) - 1.2) < 0.08
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    for at, expected in (("0.1", "red"), ("0.8", "blue")):
        frame = tmp_path / f"frame-{at}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", at, "-i", result.filepath,
                        "-frames:v", "1", "-y", str(frame)], check=True)
        with Image.open(frame) as image:
            assert image.size == (1920, 1080)
            for x, y in ((8, 8), (1911, 8), (8, 1071), (1911, 1071), (960, 540)):
                r, g, b = image.getpixel((x, y))
                assert (r > 150 and g < 100 and b < 100) if expected == "red" else (b > 130 and r < 100)


def test_stock_story_accepts_remote_only_voice_and_footage(tmp_path):
    sample = stock_reel()
    add_audio(sample, tmp_path / "voice.wav")
    block = sample.blocks[0]
    block.assets.voice_filepath = "/missing/voice.wav"
    block.assets.voice_url = "https://storage.example/voice.wav"
    block.assets.media_url_map[block.media[0].id] = "https://storage.example/clip.mp4"
    block.assets.lipsync_url = "https://storage.example/unused-avatar.mp4"
    command = EditTemplate.get("stock_story")(TemplateConfig()).compose(sample)
    assert {value["url"] for value in command.inputs if isinstance(value, dict)} == {
        "https://storage.example/voice.wav", "https://storage.example/clip.mp4",
    }


def test_stock_story_fails_when_footage_is_missing(tmp_path):
    sample = stock_reel()
    add_audio(sample, tmp_path / "voice.wav")
    with pytest.raises(ValueError, match="Missing rendered asset"):
        EditTemplate.get("stock_story")(TemplateConfig()).compose(sample)


def test_formal_orchestration_avoids_unused_providers():
    config = ShortsConfig(avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
                          video_template=VideoTemplate(edit_template="lecture", template_config={}),
                          enabled_tags=[],
                          ffmpeg_config=FFmpegConfig(provider="local_ffmpeg"), slides_config=SlidesConfig(provider_config={"upload": False}))
    with patch("aishorts.shorts_generator.ScriptGenerator") as script, patch("aishorts.shorts_generator.SubtitleGenerator"), \
         patch("aishorts.shorts_generator.ImageGenerator") as images, patch("aishorts.shorts_generator.LipsyncGenerator") as lipsync, \
         patch("aishorts.shorts_generator.ManimGenerator") as manim, patch("aishorts.shorts_generator.SongGenerator") as song:
        generator = ShortsGenerator(config)
    for unused in (lipsync, manim, song):
        unused.assert_not_called()
    images.assert_called_once()
    assert script.call_args.kwargs["generate_image"]
    assert script.call_args.kwargs["generate_latex"]
    assert "formal presentation" in script.call_args.kwargs["base_instructions"]
    assert "profanity" not in script.call_args.kwargs["base_instructions"].split("SOURCE AND VOICE")[0]
    assert AssetType.SLIDES in generator.secondary_generators
    assert AssetType.STOCK_VIDEO not in generator.required_assets
    assert generator.video_gen.render.compression_profile == "high_quality"


def test_math_orchestration_requires_manim_and_matches_the_slide_palette():
    config = ShortsConfig(
        avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
        video_template=VideoTemplate(edit_template="math", template_config={
            "presentation_style": {"theme": "midnight", "accent_color": "#E27934"}}),
        ffmpeg_config=FFmpegConfig(provider="local_ffmpeg"),
        slides_config=SlidesConfig(provider_config={"upload": False}),
    )
    with patch("aishorts.shorts_generator.ScriptGenerator") as script, \
         patch("aishorts.shorts_generator.SubtitleGenerator"), \
         patch("aishorts.shorts_generator.LatexGenerator"), \
         patch("aishorts.shorts_generator.ManimGenerator") as manim:
        manim.return_value.manim_provider.endpoint_url = None
        with pytest.raises(ValueError, match="MODAL_MANIM_ENDPOINT_URL"):
            ShortsGenerator(config)
        manim.return_value.manim_provider.endpoint_url = "https://example.test/render"
        ShortsGenerator(config)
        config.enabled_tags = []
        ShortsGenerator(config)
    assert manim.call_args.kwargs["failure_mode"] == "error"
    assert manim.call_args.kwargs["upload"] is True
    assert manim.call_args.kwargs["min_duration_seconds"] == 8
    instructions = manim.call_args.kwargs["base_instructions"]
    assert "ManimColor('#0C1921')" in instructions
    assert "ManimColor('#F2F6F3')" in instructions
    assert "ManimColor('#E27934')" in instructions
    assert "initial axes and labels in the first frame" in instructions
    assert "10-16 seconds of meaningful motion" in instructions
    assert script.call_args_list[0].kwargs["generate_manim"] is True
    assert script.call_args.kwargs["generate_manim"] is False
    assert manim.call_count == 2
    assert "MATH LESSON" in script.call_args.kwargs["base_instructions"]
    assert "complete 3-5 minute lesson" in script.call_args.kwargs["base_instructions"]
    assert "one Manim scene for every three scenes" in script.call_args.kwargs["base_instructions"]


def test_stock_story_orchestration_uses_voice_and_required_stock_only(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_VIDEO_MANIFEST", raising=False)
    config = ShortsConfig(
        avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
        video_template=VideoTemplate(edit_template="stock_story", template_config={}),
        ffmpeg_config=FFmpegConfig(provider="local_ffmpeg"),
        stock_video_config=StockVideoConfig(provider="library", provider_config={"manifest_path": str(
            Path(__file__).resolve().parents[1] / "examples/formal/stock/manifest.json")}),
    )
    with patch("aishorts.shorts_generator.ScriptGenerator") as script:
        generator = ShortsGenerator(config)
    assert set(generator.required_assets) == {
        AssetType.SCRIPT, AssetType.VOICE, AssetType.SUBTITLES, AssetType.STOCK_VIDEO,
    }
    assert generator.image_gen is None and generator.slide_gen is None
    assert generator.lipsync_gen is None
    assert AssetType.STATICFACE not in generator.required_assets
    assert generator.stock_video_gen.failure_mode == "error"
    assert script.call_args.kwargs["require_stock_video"] is True
    assert script.call_args.kwargs["generate_slides"] is False
    assert "full-screen stock footage" in script.call_args.kwargs["base_instructions"]
    config.stock_video_config = StockVideoConfig(provider="library")
    with pytest.raises(ValueError, match="requires PIXABAY_API_KEY, PEXELS_API_KEY, or a configured stock video library"):
        ShortsGenerator(config)


def test_catalog_install_and_routing_metadata(tmp_path):
    import os
    before = dict(os.environ)
    try:
        from api.install_formal_templates import install_templates
        from api.catalog import list_video_templates
        from api.plan_service import load_plan_catalog
        from api.intent_parser import _serialize_input
        from api.models import PlanRequest, VideoTemplate as DBTemplate, GenerationConfig
    finally:
        os.environ.clear()
        os.environ.update(before)
    from sqlmodel import SQLModel, Session, create_engine, select
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        install_templates(session)
        assert not session.exec(select(DBTemplate)).all()
        install_templates(session, apply=True)
        existing = session.exec(select(DBTemplate).where(DBTemplate.name == "lecture")).one()
        existing.credits = 7
        session.add(existing)
        session.commit()
        install_templates(session, apply=True)
        templates = {t.name: t for t in list_video_templates(session)}
        assert len(templates) == 5
        assert templates["lecture"].credits == 7
        assert templates["lecture"].width == 1920
        assert templates["briefing"].height == 1920
        assert templates["math"].width == 1920
        assert any(tag.asset_type == "manim" for tag in templates["math"].tags)
        assert templates["stock_story"].width == 1920
        assert templates["stock_story"].tags == []
        assert all(not any(tag.asset_type in {"images", "latex"} for tag in template.tags)
                   for template in templates.values())
        prompt = _serialize_input(PlanRequest(instruction="formal lecture"), load_plan_catalog(session), None)
        assert "16:9 narrated lesson" in prompt
        assert "stock_video" in prompt

        for name in templates:
            for suffix in (".mp4", ".png"):
                (tmp_path / f"{name}{suffix}").write_bytes(b"preview")
        storage = Mock()
        storage.upload_file.side_effect = lambda _, key: f"https://media.example/{key}"
        with patch("aishorts.utils.r2_handler.CloudflareR2", return_value=storage):
            install_templates(session, apply=True, previews=tmp_path, refresh_previews=True)
            install_templates(session, apply=True, previews=tmp_path, refresh_previews=True)
        assert storage.upload_file.call_count == 10
        assert existing.credits == 7
        assert existing.preview_url.startswith("https://media.example/assets/template-previews/lecture-")
    config = GenerationConfig(name="formal", data={"slides_config": {"provider": "pillow"}, "stock_video_config": {"provider": "library"}}).to_config_kwargs()
    assert config["stock_video_config"].provider == "library"


def test_field_guide_catalog_entry_migrates_to_stock_story(tmp_path):
    from api.install_formal_templates import install_templates
    from api.models import VideoTemplate as DBTemplate
    from sqlmodel import SQLModel, Session, create_engine, select

    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        old = DBTemplate(name="field_guide", data={"edit_template": "field_guide", "template_config": {"music": "custom.mp3"}},
                         credits=7, preview_url="https://example.test/old.mp4", thumbnail_url="https://example.test/old.png")
        session.add(old)
        session.commit()
        assert any("Replace field_guide" in change for change in install_templates(session))
        assert session.exec(select(DBTemplate).where(DBTemplate.name == "field_guide")).first()
        install_templates(session, apply=True)
        updated = session.exec(select(DBTemplate).where(DBTemplate.name == "stock_story")).one()
        assert updated.id == old.id
        assert updated.credits == 7
        assert updated.data == {"edit_template": "stock_story", "template_config": {"music": "custom.mp3"}}
        assert updated.preview_url is None and updated.thumbnail_url is None
        assert session.exec(select(DBTemplate).where(DBTemplate.name == "field_guide")).first() is None


def test_stock_story_pipeline_generates_footage_thumbnail(tmp_path, monkeypatch):
    import shutil
    import aishorts.shorts_generator as pipeline

    monkeypatch.chdir(tmp_path)
    clip_path = tmp_path / "clouds.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=0.2",
                    "-c:v", "libx264", "-y", str(clip_path)], check=True)
    storage = tmp_path / "storage"

    class Storage:
        def upload_file(self, source, key):
            target = storage / key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return f"https://storage.example/{key}"

    class Voice:
        async def populate_reel(self, sample):
            path = tmp_path / "voice.wav"
            add_audio(sample, path)

    class Stock:
        provider = SimpleNamespace(available=True)
        failure_mode = "error"

        async def populate_reel(self, sample):
            for block in sample.blocks:
                block.assets.media_map[block.media[0].id] = str(clip_path)

    llm = SimpleNamespace(generate_structure=AsyncMock(return_value=ReelSeries(topic="Learning", reels=[stock_reel()])))
    monkeypatch.setattr("aishorts.modules.script.script_generator.LLMProvider.get", lambda name: lambda **kw: llm)
    monkeypatch.setattr(pipeline, "VoiceGenerator", lambda **kw: Voice())
    monkeypatch.setattr(pipeline, "StockVideoGenerator", lambda **kw: Stock())
    monkeypatch.setattr(pipeline, "SubtitleGenerator", lambda **kw: SimpleNamespace(populate_reel=AsyncMock()))
    monkeypatch.setattr(pipeline, "CloudflareR2", Storage)
    config = ShortsConfig(
        avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
        video_template=VideoTemplate(edit_template="stock_story", template_config={}),
        ffmpeg_config=FFmpegConfig(provider="local_ffmpeg", encoder_preset="ultrafast"),
    )
    generator = ShortsGenerator(config)
    generator.video_gen.render.video_codec = "libx264"
    result = asyncio.run(generator.generate_shorts_async(user_input="Explain clouds", keep_assets=True))
    assert result.reels[0].presigned_url.startswith("https://storage.example/generated/")
    assert result.thumbnail_url == result.reels[0].thumbnail_url
    thumbnail = next((storage / "generated/thumbnails").glob("*.png"))
    with Image.open(thumbnail) as image:
        assert image.size == (960, 540)
        r, g, b = image.getpixel((8, 8))
        assert b > 130 and r < 100


def test_full_pipeline_and_ephemeral_checkpoint_resume(tmp_path, monkeypatch):
    """Real script validation, stages, storage pairs, renderer, and resume flow."""
    import shutil
    import aishorts.shorts_generator as pipeline

    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "storage"

    class Storage:
        bucket = "test"

        def upload_file(self, source, key):
            target = storage / key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return f"https://storage.example/{key}"

    async def download(url, full_path, **kwargs):
        if isinstance(url, dict):
            url = url["url"]
        key = url.removeprefix("https://storage.example/")
        shutil.copyfile(storage / key, full_path)
        return full_path

    class Voice:
        calls = 0

        async def populate_reel(self, sample):
            self.calls += 1
            path = Path("output/narration.wav")
            path.parent.mkdir(parents=True, exist_ok=True)
            add_audio(sample, path)
            for block in sample.blocks:
                block.assets.voice_url = Storage().upload_file(str(path), "voice/narration.wav")

    voice = Voice()
    llm = SimpleNamespace(generate_structure=AsyncMock(return_value=ReelSeries(topic="Learning", reels=[reel()])))
    monkeypatch.setattr("aishorts.modules.script.script_generator.LLMProvider.get", lambda name: lambda **kw: llm)
    monkeypatch.setattr(pipeline, "VoiceGenerator", lambda **kw: voice)
    monkeypatch.setattr(pipeline, "SubtitleGenerator", lambda **kw: SimpleNamespace(populate_reel=AsyncMock()))
    monkeypatch.setattr(pipeline, "CloudflareR2", Storage)
    monkeypatch.setattr("aishorts.modules.slides.slide_generator.CloudflareR2", Storage)
    monkeypatch.setattr("aishorts.modules.video_edit.video_generator.download_from_url", download)
    config = ShortsConfig(avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
                          video_template=VideoTemplate(edit_template="lecture", template_config={}),
                          ffmpeg_config=FFmpegConfig(provider="local_ffmpeg", encoder_preset="ultrafast"))
    generator = ShortsGenerator(config)
    generator.video_gen.render.video_codec = "libx264"
    first = asyncio.run(generator.generate_shorts_async(user_input="Teach fair testing", keep_assets=True))
    assert first.reels[0].presigned_url.startswith("https://storage.example/generated/")
    assert first.thumbnail_url and first.reels[0].thumbnail_url
    assert voice.calls == 1
    checkpoint = next(Path("logs").glob("*/secondary_stage.json"))
    snapshot = ReelSeries.model_validate_json(checkpoint.read_text())
    # Simulate an ephemeral worker losing all intermediate files.
    for block in snapshot.reels[0].blocks:
        Path(block.assets.voice_filepath).unlink(missing_ok=True)
        for path in block.assets.media_map.values():
            Path(path).unlink(missing_ok=True)
    second = asyncio.run(generator.generate_shorts_async(resume_from=str(checkpoint), keep_assets=True))
    assert voice.calls == 1
    assert llm.generate_structure.await_count == 1
    assert second.reels[0].thumbnail_url == first.reels[0].thumbnail_url
    assert Path(second.reels[0].local_path).is_file()


def test_remote_only_assets_and_landscape_captions(tmp_path):
    sample = reel()
    add_audio(sample, tmp_path / "audio.wav")
    block = sample.blocks[0]
    block.assets.voice_filepath = "/missing/audio.wav"
    block.assets.voice_url = "https://storage.example/audio.wav"
    block.assets.media_url_map[block.media[0].id] = "https://storage.example/slide.png"
    command = EditTemplate.get("lecture")(TemplateConfig()).compose(sample)
    assert command.inputs[:2] == [{"url": "https://storage.example/slide.png"}, {"url": "https://storage.example/audio.wav"}]
    import re
    ass_path = re.search(r"ass='([^']+)'", command.args[1]).group(1)
    subtitles = Path(ass_path).read_text()
    assert "PlayResX: 1920" in subtitles
    assert "PlayResY: 1080" in subtitles
