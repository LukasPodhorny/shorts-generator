from aishorts.modules.manim.manim_providers import ManimProvider, ManimResult
from aishorts.modules.llm.llm_generator import LLMGenerator
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import Reel
import ast
import asyncio
import re
import subprocess
import textwrap
from pathlib import Path
from aishorts.modules.video_edit.video_edit import AssetType
from aishorts.modules.provider import MediaFile


class ManimGenerator:
    def __init__(
        self,
        provider: str = "modal_manim",
        llm_provider: str = "minimax",
        base_instructions: str = None,
        failure_mode: str = "skip",
        upload: bool = False,
        min_duration_seconds: float = 0,
        **kwargs,
    ):
        self.provider_name = provider
        self.llm_provider = llm_provider
        self.base_instructions = base_instructions or ""
        self.failure_mode = failure_mode
        self.upload = upload
        self.min_duration_seconds = min_duration_seconds

        cls = ManimProvider.get(self.provider_name)
        self.manim_provider = cls(**kwargs)
        self.llm_gen = LLMGenerator(provider=llm_provider, **kwargs)

    def _extract_code(self, text: str) -> str:
        # Try to find python code block
        match = re.search(r"```python(.*?)```", text, re.DOTALL)
        if match:
            return textwrap.dedent(match.group(1)).strip()

        # Try generic code block
        match = re.search(r"```(.*?)```", text, re.DOTALL)
        if match:
            return textwrap.dedent(match.group(1)).strip()

        # Assume the whole text is code if no blocks found
        return textwrap.dedent(text).strip()

    async def generate(self, prompt: str, retries: int = 3, **kwargs) -> ManimResult:
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                instructions = self.base_instructions
                if last_error:
                    instructions += f"\n\nIMPORTANT: Your previous attempt failed with the following error. Please fix the code to resolve it:\n{last_error}"

                response = await self.llm_gen.generate_response(
                    instructions=instructions, user_input=prompt
                )

                code = self._extract_code(response)

                if "class GenScene" not in code:
                    raise ValueError("Generated code does not contain 'class GenScene'")

                try:
                    ast.parse(code)
                except SyntaxError as se:
                    raise ValueError(
                        f"Generated code has a Python syntax error at line {se.lineno}, column {se.offset}: {se.msg}"
                    ) from se

                func = self.manim_provider.render
                result = await await_or_thread(func, code, **kwargs)
                if self.min_duration_seconds:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", result.media.path],
                        capture_output=True, text=True, timeout=30, check=True,
                    )
                    duration = float(probe.stdout.strip())
                    if duration < self.min_duration_seconds:
                        Path(result.media.path).unlink(missing_ok=True)
                        raise ValueError(
                            f"Manim clip is too short ({duration:.1f}s); make it at least "
                            f"{self.min_duration_seconds:.0f}s with meaningful intermediate steps"
                        )
                return result
            except Exception as e:
                last_error = str(e)
                print(
                    f"Manim generation attempt {attempt}/{retries} failed: {last_error}"
                )
                if attempt == retries:
                    raise e

    async def populate_reel(self, reel: Reel, **kwargs):
        """
        Iterates through the reel's blocks and generates Manim animations
        for any block that has ManimMedia. Renders all items concurrently.
        """
        # Collect all (block, media_item) pairs that need rendering
        render_items = []
        for block in reel.blocks:
            if AssetType.MANIM in block.valid_assets:
                for media_item in block.media:
                    if media_item.type == "manim":
                        render_items.append((block, media_item))

        if not render_items:
            return

        # Launch all renders concurrently
        async def _render(block, media_item):
            try:
                result = await self.generate(media_item.prompt, **kwargs)
            except Exception as e:
                if self.failure_mode == "error":
                    raise
                print(
                    f"Manim generation failed for media {media_item.id}; skipping: {e}"
                )
                return
            block.assets.media_map[media_item.id] = result.media.path
            if self.upload:
                from aishorts.utils.r2_handler import CloudflareR2
                url = await asyncio.to_thread(
                    CloudflareR2().upload_file, result.media.path, f"manim/{media_item.id}.mp4"
                )
                block.assets.media_url_map[media_item.id] = url
            elif result.media.url:
                block.assets.media_url_map[media_item.id] = result.media.url

        tasks = [_render(block, media_item) for block, media_item in render_items]
        await asyncio.gather(*tasks)
