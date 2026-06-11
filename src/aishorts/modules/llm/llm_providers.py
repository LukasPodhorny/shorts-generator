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


def _get_r2_presigned_url(key: str) -> str:
    """Generate a presigned URL for an R2 object using environment variables."""
    import boto3

    endpoint_url = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    if not all([endpoint_url, access_key, secret_key, bucket]):
        raise ValueError("R2 environment variables not configured")

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,  # 1 hour
    )
    return url


async def _ensure_local_file(
    file_ref: str, session: aiohttp.ClientSession
) -> tuple[str, bool]:
    """
    Helper to ensure a file reference is a local path.
    If it's a URL, it downloads it to a temp file.
    If it's an R2 key (starts with 'uploads/'), it generates a presigned URL and downloads.
    Returns (file_path, is_temporary).
    """
    # Check if it's an R2 key (not a URL and not a local path)
    if not file_ref.startswith(("http://", "https://")) and not os.path.isabs(file_ref):
        # Assume it's an R2 key - generate presigned URL
        file_ref = _get_r2_presigned_url(file_ref)

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
                    temperature=0.7,
                    top_p=0.9,
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
                    temperature=0.7,
                    top_p=0.9,
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
                    parts.append(
                        f"--- Document: {label} ---\n{text.strip()}\n"
                    )
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
                "The following is Markdown converted from the provided file(s). "
                "Use it as the source material.\n\n"
                + file_context
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


class Groq(LLMProvider):
    """
    Groq via OpenAI-compatible Chat Completions API.
    File uploads are not supported; files are read locally (or downloaded
    from URLs) and embedded as extracted text in the prompt.
    """

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
                    parts.append(
                        f"--- Document: {label} ---\n{text.strip()}\n"
                    )
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
                "The following is Markdown converted from the provided file(s). "
                "Use it as the source material.\n\n"
                + file_context
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
            extra_body=self._extra_body() or None,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(
                "Groq returned no parsed structured output; "
                f"finish_reason={completion.choices[0].finish_reason!r}"
            )
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
            extra_body=self._extra_body() or None,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()


class Fireworks(LLMProvider):
    """
    Fireworks AI via OpenAI-compatible Chat Completions API.
    Default model is Kimi K2.5 Thinking, which produces reasoning tokens
    automatically; reasoning_effort can be passed through to throttle them.
    File uploads are not supported; files are embedded as extracted text.
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
                    parts.append(
                        f"--- Document: {label} ---\n{text.strip()}\n"
                    )
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
                "The following is Markdown converted from the provided file(s). "
                "Use it as the source material.\n\n"
                + file_context
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
            extra_body=self._extra_body() or None,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(
                "Fireworks returned no parsed structured output; "
                f"finish_reason={completion.choices[0].finish_reason!r}"
            )
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
            extra_body=self._extra_body() or None,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()
