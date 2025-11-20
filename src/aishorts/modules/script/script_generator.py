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

    def __init__(
        self,
        base_instructions: str,
        avatar: Avatar,
        provider: str = "chatgpt",
        **kwargs,
    ):
        self.avatar = avatar
        self.provider = provider.lower()
        self.instructions = (
            base_instructions + "\n\n" + "Your avatar:\n" + avatar.instructions
        )

        cls = LLM_PROVIDERS.get(self.provider)
        if not cls:
            raise ValueError(f"Unknown LLM provider '{self.provider}'")

        self.llm = cls(instructions=self.instructions, avatar=avatar, **kwargs)

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
