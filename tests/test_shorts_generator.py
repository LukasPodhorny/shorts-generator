import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.shorts_generator import (
    ShortsGenerator,
    ShortsConfig,
    ScriptConfig,
    SubtitleConfig,
)
from aishorts.modules.video_edit.video_edit import (
    VideoTemplate,
    TemplateConfig,
    AssetType,
    SubtitleStyle,
)
from aishorts.modules.avatar import Avatar


@pytest.fixture
def mock_config():
    avatars = [
        Avatar(
            name="TestAvatar",
            instructions="",
            voice={"provider": "f5tts", "voice_id": "test_voice"},
            lipsync_provider="float",
        )
    ]
    template_config = TemplateConfig(
        bg_video="bg.mp4", music="music.mp3", subtitle_style=SubtitleStyle()
    )
    video_template = VideoTemplate(
        edit_template="gameplay", template_config=template_config
    )

    return ShortsConfig(
        avatars=avatars,
        video_template=video_template,
        script_config=ScriptConfig(),
        subtitle_config=SubtitleConfig(),
    )


@pytest.fixture
def shorts_generator(mock_config):
    with (
        patch("aishorts.shorts_generator.ScriptGenerator"),
        patch("aishorts.shorts_generator.VoiceGenerator"),
        patch("aishorts.shorts_generator.LipsyncGenerator"),
        patch("aishorts.shorts_generator.SubtitleGenerator"),
        patch("aishorts.shorts_generator.VideoGenerator"),
        patch("aishorts.shorts_generator.ImageGenerator"),
        patch("aishorts.shorts_generator.LatexGenerator"),
        patch("os.makedirs"),
        patch("logging.getLogger"),
    ):

        gen = ShortsGenerator(mock_config)
        yield gen


@pytest.mark.asyncio
async def test_generate_shorts_flow(shorts_generator):
    # Mock EditTemplate to return required assets
    with (
        patch("aishorts.shorts_generator.EditTemplate.get") as mock_edit_template_get,
    ):

        # Setup required assets
        mock_template_cls = MagicMock()
        mock_template_cls.resolve_required_assets.return_value = [
            AssetType.SCRIPT,
            AssetType.VOICE,
            AssetType.IMAGES,
            AssetType.LATEX,
            AssetType.LIPSYNC,
            AssetType.SUBTITLES,
        ]
        mock_template_cls.allowed_blocks = []
        mock_edit_template_get.return_value = mock_template_cls

        mock_reel = MagicMock()
        mock_series = MagicMock()
        mock_series.reels = [mock_reel]

        # Setup Generator Mocks
        # Note: The generator instances are attributes of shorts_generator
        shorts_generator.script_gen.generate_script = AsyncMock(
            return_value=mock_series
        )
        shorts_generator.voice_gen.generate_reel_dialogues = AsyncMock(
            return_value=["voice_result"]
        )
        shorts_generator.image_gen.get_reel_images = AsyncMock(
            return_value=["image_result"]
        )
        shorts_generator.latex_gen.get_reel_images = AsyncMock(
            return_value=["latex_result"]
        )
        shorts_generator.lipsync_gen.generate_lipsyncs = AsyncMock(
            return_value=["lipsync_result"]
        )
        shorts_generator.subtitle_gen.generate_multiple_subtitles = AsyncMock(
            return_value=["subtitle_result"]
        )
        shorts_generator.video_gen.compose = MagicMock(return_value="final_video_path")

        # Run
        results = await shorts_generator.generate_shorts_async(amount=1)

        # Assertions
        assert len(results) == 1
        assert results[0] == "final_video_path"

        # Verify calls
        # Script
        shorts_generator.script_gen.generate_script.assert_called_once()

        # Generators
        shorts_generator.voice_gen.generate_reel_dialogues.assert_called()
        shorts_generator.image_gen.get_reel_images.assert_called()
        shorts_generator.latex_gen.get_reel_images.assert_called()
        shorts_generator.lipsync_gen.generate_lipsyncs.assert_called()
        shorts_generator.subtitle_gen.generate_multiple_subtitles.assert_called()
        shorts_generator.video_gen.compose.assert_called()


def test_generate_shorts_sync_wrapper(shorts_generator):
    with patch("asyncio.run") as mock_run:
        shorts_generator.generate_shorts(amount=1)
        mock_run.assert_called_once()
