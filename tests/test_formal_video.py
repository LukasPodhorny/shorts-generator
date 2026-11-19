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

from aishorts import Avatar, FFmpegConfig, ScriptConfig, ShortsConfig, ShortsGenerator, SlidesConfig, VideoTemplate
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.modules.image.image_providers import Unsplash
from aishorts.modules.script.script import AssetType, DialogueBlock, ImageMedia, Reel, ReelSeries, SlideMedia, StockVideoMedia, Trigger
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.slides.renderer import SlideOverflowError, render_slide
from aishorts.modules.slides.slide_generator import SlideGenerator
from aishorts.modules.slides.slide_providers import ModalSlides
from aishorts.modules.slides.style import SlideRenderConfig
from aishorts.modules.stock_video.stock_video_generator import StockVideoGenerator
from aishorts.modules.stock_video.stock_video_providers import LibraryStockVideo, PexelsStockVideo
from aishorts.modules.video_edit.video_edit import TemplateConfig
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.video_generator import VideoGenerator


def slide(layout="title", **kwargs):
    values = dict(type="slide", layout=layout, title="How knowledge grows",
                  subtitle="Observe, explain, and test.", trigger=Trigger(start_word_index=0, end_word_index=5))
    if layout in {"bullets", "process", "comparison"}:
        values["items"] = [{"heading": "Observation", "body": "Notice a pattern."},
                           {"heading": "Test", "body": "Check your explanation."}]
    if layout == "chart":
        values.update(chart=[{"label": "Before", "value": -5}, {"label": "After", "value": 12}],
                      unit="points", source="Illustrative example")
    values.update(kwargs)
    return SlideMedia(**values)


def reel():
    return Reel(title="Learning", description="A concise lesson.", blocks=[DialogueBlock(
        type="dialogue", avatar="Narrator", text="Observe a pattern and test it.", media=[slide()],
    )])


def validator(mode="lecture", stock=True):
    with patch("aishorts.modules.script.script_generator.LLMProvider.get", return_value=lambda **kw: SimpleNamespace()):
        template = EditTemplate.get(mode)(TemplateConfig())
        return ScriptGenerator(base_instructions="formal", avatars=[SimpleNamespace(name="Narrator", instructions="Calm")],
                               generate_slides=True, generate_stock_video=stock, generate_image=False,
                               generate_latex=False, slide_render_config=template.render_config)


@pytest.mark.parametrize("mode", ["lecture", "documentary", "briefing"])
@pytest.mark.parametrize("layout", ["title", "bullets", "process", "comparison", "chart", "quote"])
@pytest.mark.parametrize("has_visual", [False, True])
def test_all_layouts_render_readably(mode, layout, has_visual, tmp_path):
    template = EditTemplate.get(mode)(TemplateConfig())
    config = template.render_config.model_copy(update={"has_visual": has_visual})
    path = tmp_path / "slide.png"
    render_slide(slide(layout, title="Příčina a následek: měření a ověření"), config, path)
    with Image.open(path) as image:
        assert image.size == (template.width, template.height)
        assert image.getbbox() is not None


def test_bad_chart_and_comparison_rejected():
    with pytest.raises(ValidationError, match="source"):
        slide("chart", source="")
    with pytest.raises(ValidationError, match="exactly two"):
        slide("comparison", items=[{"heading": "Alone"}])
    with pytest.raises(ValidationError):
        slide("chart", chart=[{"label": "x", "value": float("nan")}, {"label": "y", "value": 1}])


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

    assert result.reels[0].blocks[0].media[1].trigger == Trigger(start_word_index=0, end_word_index=21)
    generator.llm.generate_structure.assert_awaited_once()


@pytest.mark.parametrize(("spans", "split"), [([(0, 1), (4, 5)], 4), ([(0, 30), (0, 0)], 3)])
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
        Trigger(start_word_index=split, end_word_index=5),
    ]


@pytest.mark.parametrize("end", [4, 99])
def test_generated_slide_timing_uses_full_narration_without_retry(end):
    generator = validator(mode="documentary")
    sample = ReelSeries(topic="Learning", reels=[reel()])
    sample.reels[0].blocks[0].media[0].trigger = Trigger(start_word_index=1, end_word_index=end)
    generator.llm.generate_structure = AsyncMock(return_value=sample)

    result = asyncio.run(generator.generate_script(user_input="teach"))

    assert result.reels[0].blocks[0].media[0].trigger == Trigger(start_word_index=0, end_word_index=5)
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


def test_formal_orchestration_avoids_unused_providers():
    config = ShortsConfig(avatars=[Avatar(name="Narrator", instructions="Calm", voice={"provider": "modal_f5tts"}, lipsync_provider="float")],
                          video_template=VideoTemplate(edit_template="lecture", template_config={}),
                          enabled_tags=[],
                          ffmpeg_config=FFmpegConfig(provider="local_ffmpeg"), slides_config=SlidesConfig(provider_config={"upload": False}))
    with patch("aishorts.shorts_generator.ScriptGenerator") as script, patch("aishorts.shorts_generator.SubtitleGenerator"), \
         patch("aishorts.shorts_generator.ImageGenerator") as images, patch("aishorts.shorts_generator.LipsyncGenerator") as lipsync, \
         patch("aishorts.shorts_generator.ManimGenerator") as manim, patch("aishorts.shorts_generator.SongGenerator") as song:
        generator = ShortsGenerator(config)
    for unused in (images, lipsync, manim, song):
        unused.assert_not_called()
    assert "formal presentation" in script.call_args.kwargs["base_instructions"]
    assert "profanity" not in script.call_args.kwargs["base_instructions"].split("SOURCE AND VOICE")[0]
    assert AssetType.SLIDES in generator.secondary_generators
    assert AssetType.STOCK_VIDEO not in generator.required_assets
    assert generator.video_gen.render.compression_profile == "high_quality"


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
        assert len(templates) == 3
        assert templates["lecture"].credits == 7
        assert templates["lecture"].width == 1920
        assert templates["briefing"].height == 1920
        assert all(any(tag.asset_type == "images" and tag.default for tag in template.tags)
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
        assert storage.upload_file.call_count == 6
        assert existing.credits == 7
        assert existing.preview_url.startswith("https://media.example/assets/template-previews/lecture-")
    config = GenerationConfig(name="formal", data={"slides_config": {"provider": "pillow"}, "stock_video_config": {"provider": "library"}}).to_config_kwargs()
    assert config["stock_video_config"].provider == "library"


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
