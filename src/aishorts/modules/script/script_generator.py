from aishorts.modules.avatar import Avatar
from aishorts.modules.script.llm_providers import *
from aishorts.utils.registry import LLM_PROVIDERS
import inspect
import asyncio


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

    def _generate_instructions(self) -> str:
        pass
        """
        Build the final instruction block for the LLM.
        This merges:
        - base script JSON rules
        - avatar acting instructions
        - media/latex settings
        """

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
        if self.generate_image:
            media_rules.append(
                "- Images: ENABLED (you may generate image media objects)."
            )
        else:
            media_rules.append(
                "- Images: DISABLED (never produce image media objects)."
            )

        if self.generate_latex:
            media_rules.append(
                "- LaTeX: ENABLED (you may generate latex media objects)."
            )
        else:
            media_rules.append("- LaTeX: DISABLED (never produce latex media objects).")

        media_block = "\n".join(media_rules)

        reel_conf = ["REEL CONFIGURATION:"]
        reel_conf.append(f"- Number of reels to generate: {self.num_reels}")
        reel_block = "\n".join(reel_conf)

        media_block = "\n".join(media_rules)

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
        )

        return instructions

    def __init__(
        self,
        base_instructions: str,
        avatars: list[Avatar],
        num_reels: int = 1,
        generate_latex: bool = True,
        generate_image: bool = True,
        provider: str = "chatgpt",
        **kwargs,
    ):
        self.base_instructions = base_instructions
        self.avatars = avatars
        self.num_reels = num_reels
        self.generate_latex = generate_latex
        self.generate_image = generate_image
        self.provider = provider.lower()

        self.instructions = self._generate_instructions()

        cls = LLM_PROVIDERS.get(self.provider)
        if not cls:
            raise ValueError(f"Unknown LLM provider '{self.provider}'")

        self.llm = cls(instructions=self.instructions, **kwargs)

    async def generate_script(
        self,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        func = self.llm.generate_script

        if inspect.iscoroutinefunction(func):
            return await func(files, user_input, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return asyncio.to_thread(func, files, user_input, **kwargs)
