from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from aishorts.modules.script.script import ReelSeries
from aishorts.modules.provider import Provider
from abc import abstractmethod
import asyncio
import os
from google import genai


class LLMProvider(Provider):

    @abstractmethod
    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> ReelSeries:
        pass

    @abstractmethod
    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        pass


class ChatGPT(LLMProvider):
    provider_name = "chatgpt"

    def __init__(
        self,
        model: str = "gpt-5",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
    ):
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
            for file in uploaded:
                asyncio.create_task(self.client.files.delete(file.id))

            """
            # Cleanup files asynchronously
            for file in uploaded:
                try:
                    await self.client.files.delete(file.id)
                except Exception:
                    pass  # Ignore cleanup errors
            """

    def _build_messages(self, instructions: str, user_input: str, uploaded_files: list):
        """Build message payload for OpenAI API"""
        messages = [{"role": "developer", "content": instructions}]

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

    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        response_schema=None,
        **kwargs,
    ) -> ReelSeries:
        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        # Upload files, generate response, auto-cleanup (all async!)
        async with self._temporary_files(files or []) as uploaded_files:
            messages = self._build_messages(
                instructions, user_input or "", uploaded_files
            )

            # Async API call - doesn't block event loop
            response = await self.client.responses.parse(
                model=self.model,
                input=messages,
                max_output_tokens=self.max_output_tokens,
                text_format=response_schema,
            )

            return response.output_parsed

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        async with self._temporary_files(files or []) as uploaded_files:
            messages = self._build_messages(
                instructions, user_input or "", uploaded_files
            )

            response = await self.client.responses.parse(
                model=self.model,
                input=messages,
                max_output_tokens=self.max_output_tokens,
            )

            # Assuming the raw text is in the .output attribute
            return response.output_text


class Gemini(LLMProvider):
    provider_name = "gemini"

    def __init__(
        self,
        model: str = "gemini-3-pro-preview",
        max_output_tokens: int = 10_000,
        api_key: str | None = None,
        **kwargs,
    ):

        self.model_name = model
        self.max_output_tokens = max_output_tokens

        key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=key)

    @asynccontextmanager
    async def _temporary_files(self, files: list[str]):

        if not files:
            yield []
            return

        uploaded = []
        try:
            for filepath in files:
                file = await asyncio.to_thread(self.client.files.upload, file=filepath)
                uploaded.append(file)
            yield uploaded

        finally:
            for file in uploaded:
                try:
                    await asyncio.to_thread(self.client.files.delete, name=file.name)
                except Exception:
                    pass

    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        response_schema=None,
        **kwargs,
    ) -> ReelSeries:
        from google.genai import types

        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        async with self._temporary_files(files or []) as uploaded_files:
            content = []
            content.extend(uploaded_files)
            if user_input:
                content.append(user_input)

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=content,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    max_output_tokens=self.max_output_tokens,
                    system_instruction=instructions,
                ),
            )

            return ReelSeries.model_validate_json(response.text)

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        from google.genai import types

        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        async with self._temporary_files(files or []) as uploaded_files:
            content = []
            content.extend(uploaded_files)
            if user_input:
                content.append(user_input)

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=content,
                config=types.GenerateContentConfig(
                    max_output_tokens=self.max_output_tokens,
                    system_instruction=instructions,
                ),
            )

            return response.text
