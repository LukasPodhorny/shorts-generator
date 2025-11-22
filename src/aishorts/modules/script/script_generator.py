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

    def _generate_instructions(
        self,
        base_instructions: str,
        avatars: list[Avatar],
        generate_latex: bool,
        generate_image: bool,
    ) -> str:
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
        for avatar in avatars:
            avatar_sections.append(f"- Avatar '{avatar.name}': {avatar.instructions}")
        avatar_block = "AVATARS:\n" + "\n".join(avatar_sections)

        # ------------------------------
        # Build media settings text
        # ------------------------------
        media_rules = ["MEDIA SETTINGS:"]
        if generate_image:
            media_rules.append(
                "- Images: ENABLED (you may generate image media objects)."
            )
        else:
            media_rules.append(
                "- Images: DISABLED (never produce image media objects)."
            )

        if generate_latex:
            media_rules.append(
                "- LaTeX: ENABLED (you may generate latex media objects)."
            )
        else:
            media_rules.append("- LaTeX: DISABLED (never produce latex media objects).")

        media_block = "\n".join(media_rules)

        # ------------------------------
        # Combine everything into final prompt
        # ------------------------------
        instructions = (
            base_instructions.strip()
            + "\n\n"
            + avatar_block
            + "\n\n"
            + media_block
            + "\n"
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
        self.avatar = avatars
        self.provider = provider.lower()
        self.instructions = self._generate_instructions(
            base_instructions, avatars, generate_latex, generate_image
        )

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
