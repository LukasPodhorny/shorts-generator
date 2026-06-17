import logging
from aishorts.modules.avatar import Avatar
from aishorts.modules.llm.llm_providers import *
from aishorts.modules.llm.llm_providers import LLMProvider
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import ReelSeries
from aishorts.modules.llm.llm_generator import LLMGenerator
from aishorts.modules.script.script import BlockType


class ScriptGenerator:
    """
    Parameters:
        avatar: Avatar
            The avatar configuration that will be used.
        api_key: str, optional
            Used by ChatGPT backend only.
        model: str, optional
            Used by ChatGPT backend only.
        max_output_tokens: int, optional
            Used by ChatGPT backend only.
    """

    def _generate_instructions(self, num_reels: int) -> str:
        """
        Build the final instruction block for the LLM.
        This merges:
        - base script JSON rules
        - avatar acting instructions
        - media/latex settings
        """

        def _bool_rule(boolean: bool, enabled_text: str, disabled_text: str):
            if boolean:
                return enabled_text
            else:
                return disabled_text

        # ------------------------------
        # Build avatar instruction text
        # ------------------------------
        avatar_sections = []
        
        for avatar in self.avatars:
            avatar_sections.append(f"- Avatar '{avatar.name}': {avatar.instructions}")
        avatar_block = "AVATARS:\n" + "\n".join(avatar_sections)

        # ------------------------------
        # Build media settings text
        # ------------------------------
        media_rules = ["MEDIA SETTINGS:"]
        media_rules.extend(
            [
                _bool_rule(
                    self.generate_image,
                    "- Images: ENABLED (you may generate image media objects).",
                    "- Images: ENABLED (you may generate image media objects).",
                ),
                _bool_rule(
                    self.generate_latex,
                    "- LaTeX: ENABLED (you may generate latex media objects).",
                    "- LaTeX: DISABLED (never produce latex media objects).",
                ),
                _bool_rule(
                    self.generate_manim,
                    "- Manim: ENABLED (you may generate manim media objects with a prompt describing the animation).",
                    "- Manim: DISABLED (never produce manim media objects).",
                ),
            ]
        )

        media_block = "\n".join(media_rules)

        # ------------------------------
        # Build allowed block settings
        # ------------------------------
        blocks_rules = ["ALLOWED BLOCKS:"]

        blocks_rules.extend(
            [
                _bool_rule(
                    BlockType.DIALOGUE in self.allowed_blocks,
                    f"- {BlockType.DIALOGUE.value} ENABLED",
                    f"- {BlockType.DIALOGUE.value} DISABLED",
                ),
                _bool_rule(
                    BlockType.QUESTION in self.allowed_blocks,
                    f"- {BlockType.QUESTION.value} ENABLED",
                    f"- {BlockType.QUESTION.value} DISABLED",
                ),
                _bool_rule(
                    BlockType.SONG in self.allowed_blocks,
                    f"- {BlockType.SONG.value} ENABLED (Generate a song with 'style_prompt', 'text', and optional 'media' triggers).",
                    f"- {BlockType.SONG.value} DISABLED",
                ),
            ]
        )

        blocks_block = "\n".join(blocks_rules)

        reel_conf = ["REEL CONFIGURATION:"]
        reel_conf.append(f"- Number of reels to generate: {num_reels}")
        reel_block = "\n".join(reel_conf)

        # ------------------------------
        # Combine everything into final prompt
        # ------------------------------
        instructions = (
            self.base_instructions.strip()
            + "\n\n"
            + avatar_block
            + "\n\n"
            + media_block
            + "\n\n"
            + reel_block
            + "\n\n"
            + blocks_block
        )

        return instructions

    def __init__(
        self,
        base_instructions: str = None,
        avatars: list[Avatar] = None,
        generate_latex: bool = True,
        generate_image: bool = True,
        generate_manim: bool = False,
        provider: str = "chatgpt",
        allowed_blocks: list[BlockType] = None,
        **kwargs,
    ):
        self.base_instructions = base_instructions
        self.avatars = avatars
        self.generate_latex = generate_latex
        self.generate_image = generate_image
        self.generate_manim = generate_manim
        self.allowed_blocks = allowed_blocks
        self.provider = provider.lower()
        self.logger = logging.getLogger("ShortsGenerator.ScriptGenerator")

        cls = LLMProvider.get(self.provider)
        self.llm = cls(**kwargs)

    async def generate_script(
        self,
        num_reels: int = 1,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> ReelSeries:
        instructions = self._generate_instructions(num_reels)
        self.logger.info("Script generator instructions:\n%s", instructions)
        self.logger.info(
            "Script generator sources: files=%s links=%s", files, links
        )
        self.logger.info("Script generator user_input:\n%s", user_input)
        func = self.llm.generate_structure

        return await await_or_thread(
            func,
            instructions=instructions,
            files=files,
            links=links,
            user_input=user_input,
            response_schema=ReelSeries,
            **kwargs,
        )
