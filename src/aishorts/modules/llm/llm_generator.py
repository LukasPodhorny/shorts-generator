from aishorts.modules.avatar import Avatar
from aishorts.modules.llm.llm_providers import *
from aishorts.modules.llm.llm_providers import LLMProvider
from aishorts.utils.async_utils import await_or_thread


class LLMGenerator:

    def __init__(
        self,
        provider: str = "chatgpt",
        **kwargs,
    ):
        self.provider = provider.lower()

        cls = LLMProvider.get(self.provider)
        self.llm = cls(**kwargs)

    async def generate_response(
        self,
        instructions: str | None = None,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        func = self.llm.generate_response
        return await await_or_thread(
            func,
            instructions=instructions,
            files=files,
            links=links,
            user_input=user_input,
            **kwargs,
        )
