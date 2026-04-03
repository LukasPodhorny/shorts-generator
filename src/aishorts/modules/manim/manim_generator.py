from aishorts.modules.manim.manim_providers import ManimProvider, ManimResult
from aishorts.modules.llm.llm_generator import LLMGenerator
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import Reel
import re
import textwrap
from aishorts.modules.video_edit.video_edit import AssetType
from aishorts.modules.provider import MediaFile


class ManimGenerator:
    def __init__(
        self,
        provider: str = "modal_manim",
        llm_provider: str = "minimax",
        base_instructions: str = None,
        **kwargs,
    ):
        self.provider_name = provider
        self.llm_provider = llm_provider
        self.base_instructions = base_instructions

        cls = ManimProvider.get(self.provider_name)
        if not cls:
            raise ValueError(f"Unknown Manim provider '{provider}'")

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

    async def generate(self, prompt: str, retries: int = 5, **kwargs) -> ManimResult:
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

                func = self.manim_provider.render
                return await await_or_thread(func, code, **kwargs)
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
        for any block that has ManimMedia.
        """
        for block in reel.blocks:
            if AssetType.MANIM in block.valid_assets:
                for media_item in block.media:
                    if media_item.type == "manim":
                        # Generate the animation
                        result = await self.generate(media_item.prompt, **kwargs)
                        #result = ManimResult(
                        #    media=MediaFile(
                        #        path="/home/lukaspodhorny/projects/#shorts-generator/assets/manim/manim_qubit_1.#mp4",
                        #        url="https://media.pdftoreel.com/manim/#output_5318dc2a-1e63-467a-b226-de4f77e25089.#mp4",
                        #    ),
                        #    code=""
                        #)

                        # Store the result in the block assets
                        block.assets.media_map[media_item.id] = result.media.path
                        if result.media.url:
                            block.assets.media_url_map[media_item.id] = result.media.url
