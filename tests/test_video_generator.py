import pytest
from unittest.mock import MagicMock, patch
from aishorts.modules.video_edit.video_generator import VideoGenerator, VideoTemplate
from aishorts.modules.video_edit.video_edit import TemplateConfig, SubtitleStyle


@pytest.fixture
def video_template():
    config = TemplateConfig(
        bg_video="bg.mp4", music="music.mp3", subtitle_style=SubtitleStyle()
    )
    return VideoTemplate(edit_template="gameplay", template_config=config)


@patch("aishorts.modules.video_edit.video_generator.EditTemplate.get")
@patch("aishorts.modules.video_edit.video_generator.FFmpegProvider.get")
def test_init_success(mock_ffmpeg_get, mock_edit_get, video_template):
    mock_edit_cls = MagicMock()
    mock_edit_get.return_value = mock_edit_cls

    mock_render_cls = MagicMock()
    mock_ffmpeg_get.return_value = mock_render_cls

    gen = VideoGenerator(video_template, provider="local_ffmpeg")

    mock_edit_get.assert_called_once_with("gameplay")
    mock_edit_cls.assert_called_once()

    mock_ffmpeg_get.assert_called_once_with("local_ffmpeg")
    mock_render_cls.assert_called_once()


@patch("aishorts.modules.video_edit.video_generator.EditTemplate.get")
@patch("aishorts.modules.video_edit.video_generator.FFmpegProvider.get")
def test_compose(mock_ffmpeg_get, mock_edit_get, video_template):
    # Setup mocks
    mock_edit_instance = MagicMock()
    mock_edit_get.return_value = MagicMock(return_value=mock_edit_instance)

    mock_render_instance = MagicMock()
    mock_ffmpeg_get.return_value = MagicMock(return_value=mock_render_instance)

    # Setup return values
    mock_cmd = MagicMock()
    mock_edit_instance.compose.return_value = mock_cmd
    mock_render_instance.render.return_value = "result_path"

    gen = VideoGenerator(video_template)
    result = gen.compose(template_assets=MagicMock())

    assert result == "result_path"
    mock_edit_instance.compose.assert_called_once()
    mock_render_instance.render.assert_called_once()
    # Check that render was called with the command from compose
    assert mock_render_instance.render.call_args[0][0] == mock_cmd
