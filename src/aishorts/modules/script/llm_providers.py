from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from aishorts.utils.registry import register_llm
from aishorts.modules.script.script import Script
import json
from aishorts.modules.avatar import Avatar


class BaseLLM:
    async def generate_script(
        self,
        files: list[str] | None = None,
        user_input: str | None = None,
    ) -> str:
        raise NotImplementedError("Subclasses must implement generate_script()")


@register_llm("chatgpt")
class ChatGPT(BaseLLM):
    def __init__(
        self,
        instructions: str,
        model: str = "gpt-5",
        max_output_tokens: int = 1800,
        api_key: str | None = None,
    ):
        self.instructions = instructions
        self.model = model
        self.max_output_tokens = max_output_tokens
        # Use AsyncOpenAI for proper async support
        self.client = AsyncOpenAI(api_key=api_key)

    @asynccontextmanager
    async def _temporary_files(self, files: list[str]):
        if not files:
            yield []
            return

        uploaded = []
        try:
            # Upload files asynchronously
            for filepath in files:
                with open(filepath, "rb") as f:
                    file = await self.client.files.create(file=f, purpose="user_data")
                    uploaded.append(file)

            yield uploaded

        finally:
            # Cleanup files asynchronously
            for file in uploaded:
                try:
                    await self.client.files.delete(file.id)
                except Exception:
                    pass  # Ignore cleanup errors

    def _build_messages(self, user_input: str, uploaded_files: list):
        """Build message payload for OpenAI API"""
        messages = [{"role": "developer", "content": self.instructions}]

        # Build user message content
        content_parts = []

        # Add uploaded files
        for file in uploaded_files:
            content_parts.append(
                {
                    "type": "input_file",
                    "file_id": file.id,
                }
            )

        # Add user text
        if user_input:
            content_parts.append(
                {
                    "type": "input_text",
                    "text": user_input,
                }
            )

        # If we only have text (no files), use simple string format
        if len(content_parts) == 1 and content_parts[0]["type"] == "input_text":
            messages.append({"role": "user", "content": user_input})
        else:
            messages.append({"role": "user", "content": content_parts})

        return messages

    async def generate_script(
        self,
        files: list[str] | None = None,
        user_input: str | None = None,
    ) -> Script:
        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        # Upload files, generate response, auto-cleanup (all async!)
        async with self._temporary_files(files or []) as uploaded_files:
            messages = self._build_messages(user_input or "", uploaded_files)

            # Async API call - doesn't block event loop
            response = await self.client.responses.create(
                model=self.model,
                input=messages,
                max_output_tokens=self.max_output_tokens,
                reasoning={"effort": "low"},
            )

            data = json.loads(response.output_text)
            result_script = Script.model_validate(data)

            return result_script
