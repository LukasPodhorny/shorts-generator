from openai import AsyncOpenAI
from pydantic import BaseModel
from aishorts.modules.provider import Provider
from aishorts.modules.ingest import ContentIngestor
from abc import abstractmethod
import logging
import os
from google import genai

logger = logging.getLogger("ShortsGenerator.LLMProvider")


class LLMProvider(Provider):
    """
    Base class for LLM providers.

    All input sources (files and links) are converted to Markdown via the
    ingest module (MarkItDown + vision LLM for images) and embedded directly
    in the prompt, so every provider gets identical source material handling
    regardless of whether its API supports file uploads.
    """

    # Shared lazily-created ingestor (holds the MarkItDown + vision client).
    _ingestor: ContentIngestor | None = None

    @classmethod
    def ingestor(cls) -> ContentIngestor:
        if LLMProvider._ingestor is None:
            LLMProvider._ingestor = ContentIngestor()
        return LLMProvider._ingestor

    @staticmethod
    def _require_input(
        files: list[str] | None,
        links: list[str] | None,
        user_input: str | None,
    ):
        if not files and not links and not user_input:
            raise ValueError(
                "At least one of 'files', 'links' or 'user_input' must be provided"
            )

    async def _build_user_content(
        self,
        files: list[str] | None,
        links: list[str] | None,
        user_input: str | None,
    ) -> str:
        """Convert files/links to Markdown and merge with the user's text."""
        source_context = await self.ingestor().build_context(
            files=files, links=links
        )

        chunks: list[str] = []
        if source_context:
            chunks.append(
                "The following is Markdown converted from the provided "
                "file(s)/link(s). Use it as the source material.\n\n"
                + source_context
            )
        if user_input:
            chunks.append(user_input)
        user_content = "\n\n".join(chunks)

        preview_limit = 2000
        logger.info(
            "LLM user content (%d chars total, showing first %d):\n%s",
            len(user_content),
            min(len(user_content), preview_limit),
            user_content[:preview_limit],
        )
        return user_content

    @abstractmethod
    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        response_schema: type[BaseModel] | None = None,
        **kwargs,
    ) -> BaseModel:
        pass

    @abstractmethod
    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
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

    def _build_messages(self, instructions: str, user_content: str) -> list[dict]:
        return [
            {"role": "developer", "content": instructions},
            {"role": "user", "content": user_content},
        ]

    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        response_schema: type[BaseModel] | None = None,
        **kwargs,
    ) -> BaseModel:
        self._require_input(files, links, user_input)

        user_content = await self._build_user_content(files, links, user_input)
        messages = self._build_messages(instructions, user_content)

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
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        self._require_input(files, links, user_input)

        user_content = await self._build_user_content(files, links, user_input)
        messages = self._build_messages(instructions, user_content)

        response = await self.client.responses.parse(
            model=self.model,
            input=messages,
            max_output_tokens=self.max_output_tokens,
        )

        return response.output_text


class Gemini(LLMProvider):
    provider_name = "gemini"

    def __init__(
        self,
        model: str = "gemini-3-pro-preview",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
        **kwargs,
    ):

        self.model_name = model
        self.max_output_tokens = max_output_tokens

        key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=key)

    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        response_schema: type[BaseModel] | None = None,
        **kwargs,
    ) -> BaseModel:
        from google.genai import types

        self._require_input(files, links, user_input)

        user_content = await self._build_user_content(files, links, user_input)

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[user_content],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                max_output_tokens=self.max_output_tokens,
                system_instruction=instructions,
                temperature=0.7,
                top_p=0.9,
            ),
        )

        return response_schema.model_validate_json(response.text)

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        from google.genai import types

        self._require_input(files, links, user_input)

        user_content = await self._build_user_content(files, links, user_input)

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[user_content],
            config=types.GenerateContentConfig(
                max_output_tokens=self.max_output_tokens,
                system_instruction=instructions,
                temperature=0.7,
                top_p=0.9,
            ),
        )

        return response.text


class OpenAICompatibleChat(LLMProvider):
    """
    Shared implementation for providers exposing an OpenAI-compatible Chat
    Completions API (NVIDIA NIM, Groq, Fireworks, ...). Subclasses set the
    base URL / API key env var and may add extra request body params.
    """

    provider_name = None  # abstract; subclasses register themselves

    def _extra_body(self) -> dict:
        return {}

    def _build_messages(self, instructions: str, user_content: str) -> list[dict]:
        return [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ]

    async def generate_structure(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        response_schema: type[BaseModel] | None = None,
        **kwargs,
    ) -> BaseModel:
        self._require_input(files, links, user_input)
        if response_schema is None:
            raise ValueError("response_schema is required for structured generation")

        user_content = await self._build_user_content(files, links, user_input)
        messages = self._build_messages(instructions, user_content)

        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=response_schema,
            max_completion_tokens=self.max_output_tokens,
            extra_body=self._extra_body() or None,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(
                f"{type(self).__name__} returned no parsed structured output; "
                f"finish_reason={completion.choices[0].finish_reason!r}"
            )
        return parsed

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        self._require_input(files, links, user_input)

        user_content = await self._build_user_content(files, links, user_input)
        messages = self._build_messages(instructions, user_content)

        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=self.max_output_tokens,
            extra_body=self._extra_body() or None,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()


class Minimax(OpenAICompatibleChat):
    """MiniMax M2.5 via NVIDIA NIM (OpenAI-compatible Chat Completions API)."""

    provider_name = "minimax"

    def __init__(
        self,
        model: str = "minimaxai/minimax-m2.5",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        **kwargs,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        key = api_key or os.getenv("NVIDIA_API_KEY")
        self.client = AsyncOpenAI(api_key=key, base_url=base_url)


class Groq(OpenAICompatibleChat):
    """Groq via OpenAI-compatible Chat Completions API."""

    provider_name = "groq"

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        reasoning_effort: str | None = None,
        reasoning_format: str | None = None,
        **kwargs,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        key = api_key or os.getenv("GROQ_API_KEY")
        self.client = AsyncOpenAI(api_key=key, base_url=base_url)

        # Reasoning models (gpt-oss-*, qwen3-*) emit thinking tokens that can
        # starve the structured-JSON output budget. Default to low effort and
        # a hidden format so the JSON schema gets the full token budget.
        is_reasoning = any(
            tag in model.lower() for tag in ("gpt-oss", "qwen3", "deepseek-r1")
        )
        self.reasoning_effort = reasoning_effort or (
            "low" if is_reasoning else None
        )
        self.reasoning_format = reasoning_format or (
            "hidden" if is_reasoning else None
        )

    def _extra_body(self) -> dict:
        extra: dict = {}
        if self.reasoning_effort is not None:
            extra["reasoning_effort"] = self.reasoning_effort
        if self.reasoning_format is not None:
            extra["reasoning_format"] = self.reasoning_format
        return extra


class Fireworks(OpenAICompatibleChat):
    """
    Fireworks AI via OpenAI-compatible Chat Completions API.
    Default model is Kimi K2.5 Thinking, which produces reasoning tokens
    automatically; reasoning_effort can be passed through to throttle them.
    """

    provider_name = "fireworks"

    def __init__(
        self,
        model: str = "accounts/fireworks/models/kimi-k2-thinking",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
        base_url: str = "https://api.fireworks.ai/inference/v1",
        reasoning_effort: str | None = None,
        **kwargs,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        key = api_key or os.getenv("FIREWORKS_API_KEY")
        self.client = AsyncOpenAI(api_key=key, base_url=base_url)
        self.reasoning_effort = reasoning_effort

    def _extra_body(self) -> dict:
        extra: dict = {}
        if self.reasoning_effort is not None:
            extra["reasoning_effort"] = self.reasoning_effort
        return extra
