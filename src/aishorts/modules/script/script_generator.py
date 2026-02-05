from aishorts.modules.avatar import Avatar
from aishorts.modules.script.llm_providers import *
from aishorts.modules.script.llm_providers import LLMProvider
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import ReelSeries


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
        reel_conf.append(f"- Number of reels to generate: {num_reels}")
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
        generate_latex: bool = True,
        generate_image: bool = True,
        provider: str = "chatgpt",
        **kwargs,
    ):
        self.base_instructions = base_instructions
        self.avatars = avatars
        self.generate_latex = generate_latex
        self.generate_image = generate_image
        self.provider = provider.lower()

        cls = LLMProvider.get(self.provider)
        if not cls:
            raise ValueError(f"Unknown LLM provider '{self.provider}'")

        self.llm = cls(**kwargs)

    async def generate_script(
        self,
        num_reels: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> ReelSeries:
        instructions = self._generate_instructions(num_reels)
        func = self.llm.generate_script

        return await await_or_thread(func, instructions, files, user_input, **kwargs)
