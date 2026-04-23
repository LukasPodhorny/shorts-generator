import asyncio
import os
from dataclasses import dataclass
from typing import Optional, List, Union, Dict
from pathlib import Path
import aiohttp
from aishorts.modules.provider import Provider
from abc import abstractmethod
import subprocess
import tempfile
import requests
from aishorts.utils.r2_handler import CloudflareR2, download_from_url
from aishorts.modules.video_edit.video_edit import FFmpegCommand
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from aishorts.utils.runpod_caller import EndpointCaller


@dataclass
class FFmpegResult:
    """Result from FFmpeg processing"""

    download_url: str
    filepath: str
    key: Optional[str] = None
    duration: Optional[str] = None  # Video duration in "MM:SS" or "HH:MM:SS" format


class FFmpegProvider(Provider):

    OUTPUT_DIR = "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def __init__(
        self,
        download_results: bool = True,
        compression_profile: str = "balanced",
        quality_value: int | None = None,
        max_video_bitrate: str | None = "3M",
        audio_bitrate: str = "128k",
        encoder_preset: str | None = None,
        **kwargs,
    ):
        self.download_results = download_results
        self.compression_profile = compression_profile
        self.quality_value = quality_value
        self.max_video_bitrate = max_video_bitrate
        self.audio_bitrate = audio_bitrate
        self.encoder_preset = encoder_preset

    @staticmethod
    def _has_any_flag(args: List[str], flags: List[str]) -> bool:
        return any(flag in args for flag in flags)

    def get_compression_options(
        self, codec: str, existing_args: List[str]
    ) -> List[str]:
        """
        Build lossy compression flags unless caller already provided explicit quality flags.
        For NVENC: uses capped VBR with -b:v as target, -maxrate as ceiling.
        For libx264: uses CRF with optional maxrate ceiling.
        """
        options: List[str] = []
        profile = (self.compression_profile or "balanced").lower()

        if codec == "h264_nvenc":
            if self._has_any_flag(existing_args, ["-cq", "-qp", "-b:v", "-rc"]):
                return options

            # NVENC quality levels (lower = better quality, larger file)
            profile_to_cq = {
                "high_quality": 21,
                "balanced": 26,
                "small": 30,
                "very_small": 35,
            }
            cq = (
                self.quality_value
                if self.quality_value is not None
                else profile_to_cq.get(profile, 26)
            )
            preset = self.encoder_preset or (
                "p5" if profile == "high_quality" else "p4"
            )

            # Use VBR mode with target bitrate and max bitrate cap
            # This ensures the video stays close to target while allowing quality flexibility
            if self.max_video_bitrate:
                # Target bitrate is slightly below max for headroom
                target_bitrate = self.max_video_bitrate
                options.extend(
                    [
                        "-rc",
                        "vbr",
                        "-b:v",
                        target_bitrate,
                        "-maxrate",
                        self.max_video_bitrate,
                        "-bufsize",
                        self.max_video_bitrate,
                        "-cq",
                        str(cq),
                        "-preset",
                        preset,
                        "-tune",
                        "hq",
                    ]
                )
            else:
                # No bitrate limit - use constant quality mode
                options.extend(
                    [
                        "-rc",
                        "vbr",
                        "-cq",
                        str(cq),
                        "-preset",
                        preset,
                        "-tune",
                        "hq",
                    ]
                )
        else:
            # libx264 / software encoding
            if self._has_any_flag(existing_args, ["-crf", "-qp", "-b:v"]):
                return options

            profile_to_crf = {
                "high_quality": 20,
                "balanced": 24,
                "small": 28,
                "very_small": 35,
            }
            crf = (
                self.quality_value
                if self.quality_value is not None
                else profile_to_crf.get(profile, 24)
            )
            preset = self.encoder_preset or (
                "slow" if profile == "high_quality" else "medium"
            )
            options.extend(["-crf", str(crf), "-preset", preset])
            if self.max_video_bitrate:
                options.extend(
                    [
                        "-maxrate",
                        self.max_video_bitrate,
                        "-bufsize",
                        self.max_video_bitrate,
                    ]
                )

        if (
            not self._has_any_flag(existing_args, ["-b:a", "-acodec", "-c:a"])
            and self.audio_bitrate
        ):
            options.extend(["-b:a", self.audio_bitrate])

        return options

    @abstractmethod
    async def render(
        self, cmd: FFmpegCommand, output_filename: str, **kwargs
    ) -> FFmpegResult:
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


class LocalFFmpeg(FFmpegProvider):
    provider_name = "local_ffmpeg"
    video_codec = video_codec = (
        "h264_nvenc" if FFmpegProvider.nvenc_available() else "libx264"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    async def render(
        self, cmd: FFmpegCommand, output_filename: str, **kwargs
    ) -> FFmpegResult:
        cmd.video_codec = self.video_codec

        output_path = os.path.join(self.OUTPUT_DIR, output_filename)

        # Handle dict inputs (URLs) for local FFmpeg
        resolved_inputs = []
        for inp in cmd.inputs:
            if isinstance(inp, dict):
                resolved_inputs.append(inp.get("url", ""))
            else:
                resolved_inputs.append(str(inp))

        compression_options = self.get_compression_options(self.video_codec, cmd.args)
        ffmpeg_command = cmd.to_command_list(resolved_inputs)
        ffmpeg_command.extend(compression_options)
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


class RunpodFFmpeg(EndpointCaller, FFmpegProvider):
    provider_name = "runpod_ffmpeg"

    def __init__(
        self,
        endpoint_id: str | None = None,
        runpod_api_key: str | None = None,
        timeout: int = 1800,  # Videos might take longer to render than TTS
        download_results: bool = True,
        **kwargs,
    ):
        self.endpoint_id = endpoint_id or os.getenv("FFMPEG_ENDPOINT_ID")
        super().__init__(
            endpoint_id=self.endpoint_id, timeout=timeout, api_key=runpod_api_key
        )
        FFmpegProvider.__init__(self, download_results=download_results, **kwargs)

        # Instantiate your Cloudflare R2 handler if needed for uploads/downloads
        self.r2 = CloudflareR2()
        self.session_id = kwargs.get("session_id", "default")

    async def _prepare_inputs(
        self, cmd: FFmpegCommand, session_id: str
    ) -> List[Union[str, Dict]]:
        """
        Processes cmd.inputs. If they are local Path objects, uploads them to R2
        and gets a presigned URL. If they are already URLs, keeps them as is.
        """
        processed_inputs = []

        # You might want to upload concurrency if there are multiple local files
        for input_item in cmd.inputs:
            if isinstance(input_item, Path) or (
                isinstance(input_item, str)
                and not str(input_item).startswith("http")
                and os.path.exists(str(input_item))
            ):
                # Assuming your CloudflareR2 handler has an upload method that returns a URL
                # Adjust based on your actual CloudflareR2 implementation
                remote_key = f"uploads/{session_id}/{os.path.basename(str(input_item))}"
                self.r2.upload_file(str(input_item), remote_key)

                # Get a presigned GET URL for Runpod to download
                presigned_url = self.r2.create_presigned_url(remote_key)
                processed_inputs.append(presigned_url)

            elif isinstance(input_item, dict):
                # If you already pass {"url": "...", "cache_key": "..."} handles caching
                processed_inputs.append(input_item)
            else:
                # Already a URL string
                processed_inputs.append(str(input_item))

        return processed_inputs

    async def render(
        self, cmd: FFmpegCommand, output_filename: str, **kwargs
    ) -> FFmpegResult:
        # 1. Prepare inputs (upload local files to R2 if necessary)
        session_id = kwargs.get("session_id", self.session_id)
        prepared_inputs = await self._prepare_inputs(cmd, session_id=session_id)

        # 2. Tell the Runpod worker where to upload the final video (R2 Key)
        output_key = kwargs.get("output_key", f"videos/output/{output_filename}")

        # 3. Construct the payload for Runpod
        codec = cmd.video_codec or "h264_nvenc"
        payload = {
            "input": {
                "inputs": prepared_inputs,
                "args": cmd.args,
                # Force h264_nvenc since Runpod has NVIDIA GPUs
                "video_codec": codec,
                "output_key": output_key,
                "ffmpeg_options": self.get_compression_options(codec, cmd.args),
            }
        }

        # 4. Call the Runpod Endpoint using your EndpointCaller
        # run_async handles the polling and returns the "output" part of the Runpod JSON response
        print(f"[{self.provider_name}] Sending render job to Runpod...")
        result = await self.run_async(payload)

        # 5. Handle the result
        if "error" in result:
            raise Exception(
                f"Runpod FFmpeg failed: {result['error']}\nLogs: {result.get('logs')}"
            )

        download_url = self.r2.get_public_url(output_key)
        duration = result.get("duration")  # Extract duration from response

        # Download locally if requested
        local_filepath = ""
        if self.download_results:
            local_filepath = await download_from_url(download_url, self.OUTPUT_DIR)

        return FFmpegResult(
            download_url=download_url,
            filepath=local_filepath,
            key=output_key,
            duration=duration,
        )


class ModalFFmpeg(FFmpegProvider):
    provider_name = "modal_ffmpeg"

    def __init__(
        self,
        endpoint_url: str | None = None,  # Deprecated: use gpu/cpu urls
        gpu_endpoint_url: str | None = None,
        cpu_endpoint_url: str | None = None,
        modal_api_key: str | None = None,
        download_results: bool = True,
        **kwargs,
    ):
        # The Modal ffmpeg app now exposes two endpoints: one with an L4 GPU
        # for NVENC, and a CPU-only one for libx264. Route per-codec so we
        # don't pay for GPU on software-encoded jobs.
        # Formats:
        #   https://<user>--pdftoreel-ffmpeg-ffmpeg-endpoint.modal.run       (GPU)
        #   https://<user>--pdftoreel-ffmpeg-ffmpeg-cpu-endpoint.modal.run   (CPU)
        legacy = endpoint_url or os.getenv("MODAL_FFMPEG_ENDPOINT_URL")
        self.gpu_endpoint_url = (
            gpu_endpoint_url or os.getenv("MODAL_FFMPEG_GPU_ENDPOINT_URL") or legacy
        )
        self.cpu_endpoint_url = (
            cpu_endpoint_url or os.getenv("MODAL_FFMPEG_CPU_ENDPOINT_URL") or legacy
        )
        self.modal_api_key = modal_api_key or os.getenv("MODAL_API_KEY")

        super().__init__(download_results=download_results, **kwargs)
        self.r2 = CloudflareR2()
        self.session_id = kwargs.get("session_id", "default")

    def _endpoint_for_codec(self, codec: str) -> str:
        if codec == "h264_nvenc":
            url = self.gpu_endpoint_url
            if not url:
                raise ValueError(
                    "NVENC requested but no GPU endpoint configured "
                    "(set MODAL_FFMPEG_GPU_ENDPOINT_URL)"
                )
            return url
        url = self.cpu_endpoint_url
        if not url:
            raise ValueError(
                "No CPU endpoint configured "
                "(set MODAL_FFMPEG_CPU_ENDPOINT_URL)"
            )
        return url

    async def _prepare_inputs(
        self, cmd: FFmpegCommand, session_id: str
    ) -> List[Union[str, Dict]]:
        processed_inputs = []
        for input_item in cmd.inputs:
            if isinstance(input_item, Path) or (
                isinstance(input_item, str)
                and not str(input_item).startswith("http")
                and os.path.exists(str(input_item))
            ):
                remote_key = f"uploads/{session_id}/{os.path.basename(str(input_item))}"
                self.r2.upload_file(str(input_item), remote_key)
                presigned_url = self.r2.create_presigned_url(remote_key)
                processed_inputs.append(presigned_url)
            elif isinstance(input_item, dict):
                processed_inputs.append(input_item)
            else:
                processed_inputs.append(str(input_item))
        return processed_inputs

    def _prepare_args(self, args: List[str], session_id: str) -> List[str]:
        processed_args = []
        for arg in args:
            new_arg = arg
            import re

            path_pattern = r'(/[^"\'\s]+\.(?:ass|srt|vtt|png|jpg|jpeg))'
            matches = re.findall(path_pattern, arg)

            for local_path in matches:
                if os.path.exists(local_path):
                    remote_key = (
                        f"uploads/{session_id}/args/{os.path.basename(local_path)}"
                    )
                    self.r2.upload_file(local_path, remote_key)
                    presigned_url = self.r2.create_presigned_url(remote_key)
                    new_arg = new_arg.replace(local_path, presigned_url)

            processed_args.append(new_arg)
        return processed_args

    async def render(
        self, cmd: FFmpegCommand, output_filename: str, **kwargs
    ) -> FFmpegResult:
        session_id = kwargs.get("session_id", self.session_id)
        prepared_inputs = await self._prepare_inputs(cmd, session_id=session_id)
        prepared_args = self._prepare_args(cmd.args, session_id=session_id)
        output_key = kwargs.get("output_key", f"videos/output/{output_filename}")

        codec = cmd.video_codec or "h264_nvenc"
        endpoint_url = self._endpoint_for_codec(codec)
        payload = {
            "input": {
                "inputs": prepared_inputs,
                "args": prepared_args,
                "video_codec": codec,
                "output_key": output_key,
                "ffmpeg_options": self.get_compression_options(codec, prepared_args),
            }
        }

        if self.modal_api_key:
            payload["api_key"] = self.modal_api_key

        print(
            f"[{self.provider_name}] Sending {codec} render job to Modal.com "
            f"({'GPU' if codec == 'h264_nvenc' else 'CPU'} endpoint)..."
        )

        # Unlike Runpod EndpointCaller, Modal Web Endpoints are purely synchronous HTTP responses!
        # You just POST and await the JSON response without polling /status.
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint_url, json=payload, timeout=1800
            ) as response:
                if not response.ok:
                    text = await response.text()
                    raise Exception(
                        f"Modal FFmpeg failed with {response.status}: {text}"
                    )

                result = await response.json()

        download_url = self.r2.get_public_url(output_key)
        duration = result.get("duration")  # Extract duration from Modal response

        # Download locally if requested
        local_filepath = ""
        if self.download_results:
            local_filepath = await download_from_url(download_url, self.OUTPUT_DIR)

        return FFmpegResult(
            download_url=download_url,
            filepath=local_filepath,
            key=output_key,
            duration=duration,
        )
