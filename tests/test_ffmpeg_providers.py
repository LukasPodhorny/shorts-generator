import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.video_edit.ffmpeg_providers import (
    LocalFFmpeg,
    FFmpegAPI,
    FFmpegCommand,
)
from pathlib import Path


@pytest.fixture
def ffmpeg_command():
    return FFmpegCommand(
        inputs=[Path("input1.mp4"), Path("input2.mp3")],
        args=["-filter_complex", "...", "-c:v", "libx264"],
        input_labels=["video", "audio"],
    )


class TestLocalFFmpeg:
    @patch("aishorts.modules.video_edit.ffmpeg_providers.subprocess.run")
    def test_render_success(self, mock_run, ffmpeg_command):
        provider = LocalFFmpeg()

        result = provider.render(ffmpeg_command, "output.mp4")

        assert "output.mp4" in result.filepath
        assert "file://" in result.download_url

        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "ffmpeg"
        assert "input1.mp4" in cmd_args
        assert "input2.mp3" in cmd_args
        assert "-y" in cmd_args


class TestFFmpegAPI:
    @pytest.mark.asyncio
    async def test_render_flow(self, ffmpeg_command):
        # Create a subclass to mock abstract/not-implemented methods easily
        class MockFFmpegAPI(FFmpegAPI):
            provider_name = None

            async def _upload_file(self, file_path):
                return f"http://upload/{file_path.name}"

            async def _submit_job(self, command):
                return {"output_url": "http://result/output.mp4"}

            async def _download_file(self, url, dest):
                pass

        provider = MockFFmpegAPI(api_key="test")

        # Mock os.path.join to return a simple string for verification
        with patch("os.path.join", return_value="/tmp/output.mp4"):
            result = await provider.render(ffmpeg_command, "output.mp4")

        assert result.download_url == "http://result/output.mp4"
        assert result.filepath == "/tmp/output.mp4"

    def test_command_to_list(self, ffmpeg_command):
        resolved = ["http://u1", "http://u2"]
        cmd_list = ffmpeg_command.to_command_list(resolved)

        assert cmd_list[0] == "ffmpeg"
        assert cmd_list[1] == "-i"
        assert cmd_list[2] == "http://u1"
        assert cmd_list[3] == "-i"
        assert cmd_list[4] == "http://u2"
        assert "-c:v" in cmd_list
