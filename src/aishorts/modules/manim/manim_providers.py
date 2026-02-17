from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
import subprocess
import uuid
import tempfile
import shutil
import glob


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
    provider_name = "local"

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
