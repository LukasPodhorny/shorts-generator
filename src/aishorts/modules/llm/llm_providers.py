from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from aishorts.modules.script.script import ReelSeries
from aishorts.modules.script.file_reader import extract_text
from aishorts.modules.provider import Provider
from abc import abstractmethod
import asyncio
import os
from google import genai
import aiohttp
import aiofiles
import uuid
import tempfile
from urllib.parse import urlparse


async def _ensure_local_file(
    file_ref: str, session: aiohttp.ClientSession
) -> tuple[str, bool]:
    """
    Helper to ensure a file reference is a local path.
    If it's a URL, it downloads it to a temp file.
    Returns (file_path, is_temporary).
    """
    if file_ref.startswith(("http://", "https://")):
        parsed = urlparse(file_ref)
        ext = os.path.splitext(parsed.path)[1] or ".bin"
        temp_name = f"temp_llm_{uuid.uuid4()}{ext}"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)

        async with session.get(file_ref) as resp:
            resp.raise_for_status()
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)
        return temp_path, True
    return file_ref, False


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

        uploaded_files = []
        temp_paths = []

        async with aiohttp.ClientSession() as session:
            try:
                for file_ref in files:
                    # 1. Ensure we have a local file (download if URL)
                    filepath, is_temp = await _ensure_local_file(file_ref, session)
                    if is_temp:
                        temp_paths.append(filepath)

                    # 2. Upload to OpenAI
                    with open(filepath, "rb") as f:
                        file = await self.client.files.create(
                            file=f, purpose="user_data"
                        )
                        uploaded_files.append(file)

                yield uploaded_files

            finally:
                # Cleanup OpenAI files
                cleanup_tasks = [self.client.files.delete(f.id) for f in uploaded_files]
                if cleanup_tasks:
                    await asyncio.gather(*cleanup_tasks, return_exceptions=True)

                # Cleanup local temp files
                for p in temp_paths:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass

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
        max_output_tokens: int = 50_000,
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

        uploaded_files = []
        temp_paths = []

        async with aiohttp.ClientSession() as session:
            try:
                for file_ref in files:
                    # 1. Ensure we have a local file (download if URL)
                    filepath, is_temp = await _ensure_local_file(file_ref, session)
                    if is_temp:
                        temp_paths.append(filepath)

                    # 2. Upload to Gemini File API
                    # Note: Gemini Python SDK 'files.upload' takes a path string
                    file = await asyncio.to_thread(
                        self.client.files.upload, file=filepath
                    )
                    uploaded_files.append(file)

                yield uploaded_files

            finally:
                # Cleanup Gemini files
                for file in uploaded_files:
                    try:
                        await asyncio.to_thread(
                            self.client.files.delete, name=file.name
                        )
                    except Exception:
                        pass

                # Cleanup local temp files
                for p in temp_paths:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
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


class Minimax(LLMProvider):
    """
    MiniMax M2.5 via NVIDIA NIM (OpenAI-compatible Chat Completions API).
    Document uploads are not supported on NIM; files are read locally (or
    downloaded from URLs) and embedded as extracted text in the prompt.
    """

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

    async def _files_to_embedded_context(self, files: list[str]) -> str:
        if not files:
            return ""

        parts: list[str] = []
        async with aiohttp.ClientSession() as session:
            temp_paths: list[str] = []
            try:
                for file_ref in files:
                    filepath, is_temp = await _ensure_local_file(file_ref, session)
                    if is_temp:
                        temp_paths.append(filepath)
                    label = file_ref if not is_temp else os.path.basename(filepath)
                    text = await asyncio.to_thread(extract_text, filepath)
                    parts.append(f"--- Document: {label} ---\n{text.strip()}\n")
            finally:
                for p in temp_paths:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass

        return "\n\n".join(parts)

    def _build_user_content(self, file_context: str, user_input: str | None) -> str:
        chunks: list[str] = []
        if file_context:
            chunks.append(
                "The following is plain text extracted from the provided file(s). "
                "Use it as the source material.\n\n" + file_context
            )
        if user_input:
            chunks.append(user_input)
        return "\n\n".join(chunks)

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
        if response_schema is None:
            raise ValueError("response_schema is required for structured generation")

        file_context = await self._files_to_embedded_context(files or [])
        user_content = self._build_user_content(file_context, user_input)

        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ]

        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=response_schema,
            max_completion_tokens=self.max_output_tokens,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(
                "NIM returned no parsed structured output; "
                f"finish_reason={completion.choices[0].finish_reason!r}"
            )

        finish_reason = completion.choices[0].finish_reason
        if finish_reason == "length":
            raise RuntimeError(
                f"Output truncated (finish_reason={finish_reason}). "
                "Consider increasing max_output_tokens."
            )

        if hasattr(parsed, "reels") and not parsed.reels:
            raise RuntimeError("LLM returned empty reels array")

        return parsed

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        file_context = await self._files_to_embedded_context(files or [])
        user_content = self._build_user_content(file_context, user_input)

        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ]

        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=self.max_output_tokens,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()
