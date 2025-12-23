import os
from dataclasses import dataclass
import os
from typing import Optional
from dataclasses import dataclass
from aishorts.modules.provider import Provider
from abc import abstractmethod
from aishorts.modules.video_edit.video_edit import FFmpegCommand
from pathlib import Path
import subprocess
import tempfile


@dataclass
class FFmpegResult:
    """Result from FFmpeg processing"""

    download_url: str
    filepath: str


class FFmpegProvider(Provider):

    OUTPUT_DIR = "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def render(self, cmd: FFmpegCommand, **kwargs) -> FFmpegResult:
        pass

    @staticmethod
    def nvenc_available() -> bool:
        """
        Check if h264_nvenc actually works (not only exists in the encoder list).
        This tries encoding a single black frame with NVENC.
        """

        test_out = tempfile.NamedTemporaryFile(suffix=".mp4").name

        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=16x16:d=0.1",
            "-c:v",
            "h264_nvenc",
            "-y",
            test_out,
        ]

        try:
            subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
            )
            return True
        except:
            return False


class FFmpegAPI(FFmpegProvider):
    provider_name = "ffmpegapi"
    API_BASE = "https://api.ffmpeg-api.com"
    video_codec = "h264_nvenc"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FFMPEG_API_KEY")

    async def render(self, cmd: FFmpegCommand, output_filename: str) -> FFmpegResult:
        """
        Upload all inputs, build command with URLs, execute
        """
        # set video codec
        cmd.video_codec = self.video_codec

        # 1. Upload all input files and get URLs (in order!)
        resolved_inputs = []
        for i, input_path in enumerate(cmd.inputs):
            label = cmd.input_labels[i] if i < len(cmd.input_labels) else f"input_{i}"
            print(f"Uploading {label}: {input_path}")

            url = await self._upload_file(input_path)
            resolved_inputs.append(url)

        # 2. Build final command with URLs
        ffmpeg_command = cmd.to_command_list(resolved_inputs)

        # 3. Add output
        ffmpeg_command.extend(["-y", output_filename])

        # 4. Submit to API
        result = await self._submit_job(ffmpeg_command)

        # 5. Download result
        output_path = os.path.join(self.OUTPUT_DIR, output_filename)
        await self._download_file(result["output_url"], output_path)

        return FFmpegResult(download_url=result["output_url"], filepath=output_path)

    async def _upload_file(self, file_path: Path) -> str:
        """Upload file and return URL"""
        # Implementation depends on your storage (S3, R2, etc.)
        pass

    async def _submit_job(self, command: list[str]) -> dict:
        """Submit FFmpeg job to API"""
        pass

    async def _download_file(self, url: str, dest: str) -> None:
        """Download result file"""
        pass


class LocalFFmpeg(FFmpegProvider):
    provider_name = "local_ffmpeg"
    video_codec = video_codec = (
        "h264_nvenc" if FFmpegProvider.nvenc_available() else "libx264"
    )

    def __init__(self):
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    def render(self, cmd: FFmpegCommand, output_filename: str) -> FFmpegResult:
        cmd.video_codec = self.video_codec

        output_path = os.path.join(self.OUTPUT_DIR, output_filename)

        resolved_inputs = [str(path) for path in cmd.inputs]
        ffmpeg_command = cmd.to_command_list(resolved_inputs)
        ffmpeg_command.extend(["-y", output_path])

        try:
            result = subprocess.run(ffmpeg_command, check=True)
        except subprocess.CalledProcessError as e:
            # Print FFmpeg's actual error message
            print("\n" + "=" * 80)
            print("FFMPEG FAILED!")
            print("=" * 80)
            print("COMMAND:")
            print(" ".join(ffmpeg_command))
            print("\n" + "=" * 80)
            print("STDERR OUTPUT:")
            print(e.stderr)
            print("=" * 80 + "\n")
            raise

        return FFmpegResult(download_url=f"file://{output_path}", filepath=output_path)
