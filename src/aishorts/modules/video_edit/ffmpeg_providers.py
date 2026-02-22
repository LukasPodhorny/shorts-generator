import asyncio
import os
from dataclasses import dataclass
import os
from typing import Optional
from aishorts.modules.provider import Provider
from abc import abstractmethod
import subprocess
import tempfile
import requests
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.modules.video_edit.video_edit import FFmpegCommand
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class FFmpegResult:
    """Result from FFmpeg processing"""

    download_url: str
    filepath: str


class FFmpegProvider(Provider):

    OUTPUT_DIR = "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    async def render(self, cmd: FFmpegCommand, **kwargs) -> FFmpegResult:
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
    API_URL = "https://api.ffmpeg-api.com/ffmpeg/process"
    video_codec = "h264_nvenc"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key or os.getenv("FFMPEG_API_KEY")
        self.r2 = CloudflareR2()

    def _get_upload_info(self, path: str, directory_id: Optional[str] = None) -> dict:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        file_name = os.path.basename(path)

        payload = {"file_name": file_name}
        if directory_id:
            payload["dir_id"] = directory_id

        # 1. Get upload URL
        resp = requests.post(
            "https://api.ffmpeg-api.com/file",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to get upload URL ({resp.status_code}): {resp.text}"
            )

        data = resp.json()

        # Try to extract upload URL and file path
        # Handling potential nested structure "upload.url" and "file.file_path"
        upload_url = data.get("upload", {}).get("url") or data.get("url")
        file_path = data.get("file", {}).get("file_path") or data.get("file_path")

        if not upload_url or not file_path:
            raise RuntimeError(f"Invalid response from /file endpoint: {data}")

        return {"upload_url": upload_url, "file_path": file_path}

    def _upload_file_content(self, path: str, upload_url: str):
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "application/octet-stream"

        with open(path, "rb") as f:
            put_resp = requests.put(
                upload_url, data=f, headers={"Content-Type": mime_type}
            )
            put_resp.raise_for_status()

    async def render(self, cmd: FFmpegCommand, output_filename: str) -> FFmpegResult:
        if not self.api_key:
            raise ValueError(
                "FFmpeg API key is missing. Please set FFMPEG_API_KEY environment variable or pass api_key to constructor."
            )

        # 1. Register and Upload inputs
        input_file_paths = []
        directory_id = None
        upload_tasks = []

        if cmd.inputs:
            # Register all files first to get URLs and ensure same directory
            for i, path in enumerate(cmd.inputs):
                info = self._get_upload_info(str(path), directory_id)
                input_file_paths.append(info["file_path"])
                upload_tasks.append((str(path), info["upload_url"]))

                # Capture directory_id from the first file
                if i == 0 and "/" in info["file_path"]:
                    directory_id = info["file_path"].split("/")[0]

        # Upload in parallel
        print(f"Uploading {len(upload_tasks)} files in parallel...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(self._upload_file_content, path, url)
                for path, url in upload_tasks
            ]
            for future in as_completed(futures):
                future.result()  # Raise exceptions if any

        print("All uploads completed.")

        # 2. Parse args
        filter_complex = None
        maps = []
        options = []

        if cmd.video_codec:
            options.extend(["-c:v", cmd.video_codec])
        elif self.video_codec:
            options.extend(["-c:v", self.video_codec])

        i = 0
        while i < len(cmd.args):
            arg = cmd.args[i]
            if arg in ("-filter_complex", "-lavfi"):
                i += 1
                if i < len(cmd.args):
                    filter_complex = cmd.args[i]
            elif arg == "-map":
                i += 1
                if i < len(cmd.args):
                    maps.append(cmd.args[i])
            elif arg == "-y":
                pass
            else:
                options.append(arg)
            i += 1

        # 3. Construct Payload
        payload = {
            "task": {
                "inputs": [{"file_path": fp} for fp in input_file_paths],
                "outputs": [
                    {"file": output_filename, "options": options, "maps": maps}
                ],
            }
        }

        print(payload)

        if filter_complex:
            payload["task"]["filter_complex"] = filter_complex

        # 4. Call API
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}

        response = requests.post(self.API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise RuntimeError(
                f"FFmpeg API failed ({response.status_code}): {response.text}"
            )

        result_json = response.json()
        download_url = result_json.get("output_url")

        if not download_url:
            raise RuntimeError(f"No output URL in response: {result_json}")

        # 5. Download Output
        output_path = os.path.join(self.OUTPUT_DIR, output_filename)

        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        return FFmpegResult(download_url=download_url, filepath=output_path)


class LocalFFmpeg(FFmpegProvider):
    provider_name = "local_ffmpeg"
    video_codec = video_codec = (
        "h264_nvenc" if FFmpegProvider.nvenc_available() else "libx264"
    )

    def __init__(self, **kwargs):
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    async def render(self, cmd: FFmpegCommand, output_filename: str) -> FFmpegResult:
        cmd.video_codec = self.video_codec

        output_path = os.path.join(self.OUTPUT_DIR, output_filename)

        resolved_inputs = [str(path) for path in cmd.inputs]
        ffmpeg_command = cmd.to_command_list(resolved_inputs)
        ffmpeg_command.extend(["-y", output_path])

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, ffmpeg_command, output=stdout, stderr=stderr
                )
        except subprocess.CalledProcessError as e:
            # Print FFmpeg's actual error message
            print("\n" + "=" * 80)
            print("FFMPEG FAILED!")
            print("=" * 80)
            print("COMMAND:")
            print(" ".join(ffmpeg_command))
            print("\n" + "=" * 80)
            print("STDERR OUTPUT:")
            print(e.stderr.decode() if e.stderr else "No stderr captured")
            print("=" * 80 + "\n")
            raise

        return FFmpegResult(download_url=f"file://{output_path}", filepath=output_path)
