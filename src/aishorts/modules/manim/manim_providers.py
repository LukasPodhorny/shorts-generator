from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
import subprocess
import uuid
import tempfile
import shutil
import glob
import aiohttp
from aishorts.utils.r2_handler import download_from_url


@dataclass
class ManimResult:
    media: MediaFile
    code: str


class ManimProvider(Provider):
    OUTPUT_DIR = os.getenv("MANIM_OUTPUT_DIR") or "output/manim"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def render(self, code: str, **kwargs) -> ManimResult:
        pass


class LocalManim(ManimProvider):
    provider_name = "local_manim"

    def render(self, code: str, **kwargs) -> ManimResult:
        unique_id = str(uuid.uuid4())

        # Create a temporary directory for the rendering process
        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = os.path.join(tmp_dir, f"scene_{unique_id}.py")

            # Write the code to a file
            with open(script_path, "w") as f:
                f.write(code)

            # Define output filename
            output_filename = f"{unique_id}.mp4"
            final_output_path = os.path.join(self.OUTPUT_DIR, output_filename)

            # Construct manim command
            # -qm: Medium quality
            # --media_dir: where to put artifacts
            # -o: output filename
            cmd = [
                "manim",
                "-qh",  # High quality (1080p)
                "--media_dir",
                tmp_dir,
                "-o",
                output_filename,
                script_path,
                "GenScene",  # We enforce this class name in the generator
            ]

            # Run manim
            process = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp_dir
            )

            if process.returncode != 0:
                error_msg = f"Manim rendering failed.\nStdout: {process.stdout.decode()}\nStderr: {process.stderr.decode()}"
                raise RuntimeError(error_msg)

            # Find the generated file
            # Manim outputs to {media_dir}/videos/{script_name}/{quality}/{filename}
            # We search recursively to be safe
            found_files = glob.glob(
                os.path.join(tmp_dir, "**", output_filename), recursive=True
            )

            if not found_files:
                raise FileNotFoundError(
                    f"Could not find generated video {output_filename} in {tmp_dir}"
                )

            # Move to final destination
            shutil.move(found_files[0], final_output_path)

            return ManimResult(
                media=MediaFile(id=unique_id, path=final_output_path), code=code
            )


class ModalManim(ManimProvider):
    provider_name = "modal_manim"

    def __init__(
        self,
        endpoint_url: str | None = None,
        modal_api_key: str | None = None,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url or os.getenv("MODAL_MANIM_ENDPOINT_URL")
        self.modal_api_key = modal_api_key or os.getenv("MODAL_API_KEY")

    async def render(self, code: str, **kwargs) -> ManimResult:
        if not self.endpoint_url:
            raise ValueError(
                "MODAL_MANIM_ENDPOINT_URL not set. Please provide it in environment or constructor."
            )

        payload = {
            "code": code,
            "quality": kwargs.get("quality", "-qh"),
        }

        if self.modal_api_key:
            payload["api_key"] = self.modal_api_key

        print(f"[{self.provider_name}] Sending render job to Modal.com...")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url, json=payload, timeout=600
            ) as response:
                if not response.ok:
                    text = await response.text()
                    raise Exception(
                        f"Modal Manim failed with {response.status}: {text}"
                    )

                result = await response.json()

        download_url = result.get("download_url")

        # Download locally
        local_filepath = await download_from_url(download_url, self.OUTPUT_DIR)

        return ManimResult(
            media=MediaFile(
                id=str(uuid.uuid4()), url=download_url, path=local_filepath
            ),
            code=code,
        )
