from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from aishorts.modules.script.script import ReelSeries
from aishorts.modules.provider import Provider
from abc import abstractmethod
import asyncio
import os
import json
from google import genai
import aiohttp
import aiofiles
import uuid
import tempfile
from urllib.parse import urlparse

from pypdf import PdfReader


def _extract_text_from_pdf_bytes(data: bytes) -> str:
    import io

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n\n".join(parts)


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


MAX_PDF_INPUT_BYTES = 25 * 1024 * 1024


async def _minimax_read_file_as_text(
    path: str,
    name: str,
    max_plain_bytes: int,
) -> str:
    """
    Plain text: UTF-8 only, capped at max_plain_bytes.
    PDF: extract text with pypdf (same cap on extracted text length).
    """
    size = await asyncio.to_thread(lambda: os.path.getsize(path))
    pdf_by_name = name.lower().endswith(".pdf")

    async with aiofiles.open(path, "rb") as f:
        head = await f.read(8)
    pdf_by_magic = head.startswith(b"%PDF")

    if pdf_by_name or pdf_by_magic:
        if size > MAX_PDF_INPUT_BYTES:
            return (
                f"[PDF larger than {MAX_PDF_INPUT_BYTES} bytes; not read. "
                "Use a smaller file or split it.]"
            )
        async with aiofiles.open(path, "rb") as f:
            raw = await f.read()
        try:
            extracted = await asyncio.to_thread(_extract_text_from_pdf_bytes, raw)
        except Exception as e:
            return f"[Could not read PDF (encrypted or invalid): {e}]"
        extracted = (extracted or "").strip()
        if not extracted:
            return "[No extractable text in this PDF (may be scanned images only).]"
        if len(extracted) > max_plain_bytes:
            extracted = (
                extracted[:max_plain_bytes]
                + f"\n\n[... truncated to {max_plain_bytes} characters ...]"
            )
        return extracted

    if size > max_plain_bytes:
        return f"[File larger than {max_plain_bytes} bytes; not inlined]"
    try:
        async with aiofiles.open(path, "rb") as f:
            raw = await f.read()
    except OSError as e:
        return f"[Could not read: {e}]"
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return "[Binary or non-UTF-8 file; contents not inlined (not a PDF with extractable text).]"


async def _minimax_build_user_content(
    files: list[str] | None,
    user_input: str | None,
    max_bytes_per_file: int = 500_000,
) -> str:
    """
    NVIDIA NIM chat.completions has no file-upload API like OpenAI/Gemini.
    We download paths/URLs locally and inline text into the user message.
    PDFs are handled via pypdf text extraction (not OCR).
    """
    parts: list[str] = []
    if user_input:
        parts.append(user_input)
    if not files:
        return "\n\n".join(parts).strip()

    async with aiohttp.ClientSession() as session:
        file_blocks: list[str] = []
        for file_ref in files:
            path, is_temp = await _ensure_local_file(file_ref, session)
            try:
                name = os.path.basename(path) or file_ref
                text = await _minimax_read_file_as_text(
                    path, name, max_bytes_per_file
                )
                file_blocks.append(f"--- File: {name} ---\n{text}")
            finally:
                if is_temp and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        if file_blocks:
            parts.append("Attached file contents:\n\n" + "\n\n".join(file_blocks))
    return "\n\n".join(parts).strip()


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
    provider_name = "minimax"

    def __init__(
        self,
        model: str = "minimaxai/minimax-m2.5",
        max_output_tokens: int = 50_000,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens

        key = api_key or os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=base_url or "https://integrate.api.nvidia.com/v1",
        )

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        text = (text or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

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

        schema_cls = response_schema or ReelSeries
        schema = schema_cls.model_json_schema()

        schema_prompt = (
            "Return ONLY valid JSON that matches this JSON Schema exactly:\n"
            f"{json.dumps(schema, ensure_ascii=True)}"
        )

        user_content = await _minimax_build_user_content(files, user_input)
        messages = [
            {"role": "system", "content": instructions},
            {"role": "system", "content": schema_prompt},
            {"role": "user", "content": user_content},
        ]

        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_output_tokens,
        )
        text = self._strip_code_fences(completion.choices[0].message.content)
        return schema_cls.model_validate_json(text)

    async def generate_response(
        self,
        instructions: str,
        files: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> str:
        if not files and not user_input:
            raise ValueError("Either 'files' or 'user_input' must be provided")

        user_content = await _minimax_build_user_content(files, user_input)
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ]

        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_output_tokens,
        )
        return completion.choices[0].message.content or ""
