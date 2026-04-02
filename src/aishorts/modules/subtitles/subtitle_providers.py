import os
import asyncio
import aiohttp
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Union, Optional
from abc import abstractmethod

# Third-party imports
from openai import AsyncOpenAI
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment

# Project imports (assuming these are available in your environment)
from aishorts.modules.tts.tts_providers import TTSResult
from aishorts.modules.provider import Provider
from aishorts.modules.script.script import AssetType, Reel
from aishorts.utils.r2_handler import CloudflareR2


def get_wav_length(path: str):
    audio = AudioSegment.from_wav(path)
    duration = len(audio) / 1000.0
    return duration


class SubtitlesProvider(Provider):
    @abstractmethod
    async def populate_reel(self, reel: Reel, **kwargs) -> None:
        pass

    @abstractmethod
    async def generate_subtitles(
        self, audio_file: str, text: str
    ) -> TranscriptionVerbose:
        pass


class WhisperSubtitles(SubtitlesProvider):
    provider_name = "whisper"

    def __init__(
        self,
        use_lemonfox: bool = True,
        api_key: str | None = None,
        max_concurrent: int = 5,
    ):
        self.api_key = api_key or (
            os.getenv("LEMONFOX_API_KEY")
            if use_lemonfox
            else os.getenv("OPENAI_API_KEY")
        )
        base_url = "https://api.lemonfox.ai/v1" if use_lemonfox else None

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_subtitles(
        self, audio_file: str, text: str = None
    ) -> TranscriptionVerbose:
        async with self.semaphore:
            with open(audio_file, "rb") as audio:
                transcription = await self.client.audio.transcriptions.create(
                    file=audio,
                    model="whisper-1",
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                    prompt=text,
                )
            return transcription


async def populate_reel(self, reel: Reel) -> None:
    tts_results = []
    for i, block in enumerate(reel.blocks):
        if AssetType.SUBTITLES in block.valid_assets and block.assets.voice_filepath:
            tts_results.append(
                TTSResult(
                    id=i, filepath=block.assets.voice_filepath, transcription=block.text
                )
            )

    if not tts_results:
        return

    tasks = [
        self.generate_subtitles(res.filepath, res.transcription) for res in tts_results
    ]
    results = await asyncio.gather(*tasks)

    for tts_res, sub_res in zip(tts_results, results):
        reel.blocks[tts_res.id].assets.subtitles = sub_res


class ModalWav2VecAligner(SubtitlesProvider):
    provider_name = "modal_wav2vec_aligner"

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        modal_api_key: Optional[str] = None,
        r2_provider=None,
        max_concurrent: int = 3,
        min_silence_duration: float = 0.5,
        **kwargs,
    ):
        """Initialize the Wav2Vec Aligner provider."""
        self.endpoint_url = endpoint_url or os.getenv("MODAL_WAV2VEC_ENDPOINT_URL")
        self.modal_api_key = modal_api_key or os.getenv("MODAL_API_KEY")
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.min_silence_duration = min_silence_duration

        # Use existing R2 handler or initialize the standard one
        self.r2 = r2_provider or CloudflareR2()

    async def _prepare_audio(self, audio_path: Union[str, Path]) -> str:
        """Uploads local audio to R2 and returns a presigned URL."""
        audio_path_str = str(audio_path)
        if audio_path_str.startswith("http"):
            return audio_path_str

        if os.path.exists(audio_path_str):
            remote_key = f"uploads/audio/{os.path.basename(audio_path_str)}"
            print(
                f"[{self.provider_name}] Uploading {os.path.basename(audio_path_str)} to R2..."
            )
            # Wrap synchronous R2 upload in a thread to keep it non-blocking
            await asyncio.to_thread(self.r2.upload_file, audio_path_str, remote_key)
            presigned_url = self.r2.create_presigned_url(remote_key)
            return presigned_url
        else:
            raise FileNotFoundError(f"Audio file not found: {audio_path_str}")

    async def generate_subtitles(
        self, audio_file: str, text: str
    ) -> TranscriptionVerbose:
        """Alignment logic wrapped to return the expected OpenAI TranscriptionVerbose type."""
        async with self.semaphore:
            if not self.endpoint_url:
                raise ValueError("MODAL_WAV2VEC_ENDPOINT_URL is not set.")

            audio_url = await self._prepare_audio(audio_file)

            payload = {"audio_url": audio_url, "text": text}
            if self.modal_api_key:
                payload["api_key"] = self.modal_api_key

            print(
                f"[{self.provider_name}] Sending alignment job to Modal.com for {os.path.basename(audio_file)}..."
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint_url, json=payload, timeout=600
                ) as response:
                    print(
                        f"[{self.provider_name}] Modal responded with status {response.status} for {os.path.basename(audio_file)}"
                    )
                    if not response.ok:
                        err = await response.text()
                        raise Exception(
                            f"Modal Wav2Vec Alignment failed with {response.status}: {err}"
                        )
                    result = await response.json()

            # Map Modal segments to the standard TranscriptionWord format
            # and bridge gaps shorter than min_silence_duration
            words = []
            segments = result.get("segments", [])
            for i, seg in enumerate(segments):
                word_text = seg["word"]
                start = seg["start"]
                end = seg["end"]

                # If there's a next segment, check if we should bridge the gap
                if i < len(segments) - 1:
                    next_start = segments[i + 1]["start"]
                    gap = next_start - end
                    if gap < self.min_silence_duration:
                        end = next_start

                words.append(TranscriptionWord(word=word_text, start=start, end=end))

            return TranscriptionVerbose(
                duration=get_wav_length(audio_file),
                language="english",
                text=text,
                words=words,
            )

    async def populate_reel(self, reel: Reel) -> None:
        """Processes all blocks in a reel that require subtitles."""
        tts_results = []
        for i, block in enumerate(reel.blocks):
            if (
                AssetType.SUBTITLES in block.valid_assets
                and block.assets.voice_filepath
            ):
                audio_input = (
                    block.assets.voice_url
                    if block.assets.voice_url
                    else block.assets.voice_filepath
                )
                tts_results.append(
                    TTSResult(
                        id=i,
                        filepath=block.assets.voice_filepath,
                        url=audio_input,
                        transcription=block.text,
                    )
                )

        if not tts_results:
            return

        print(f"[{self.provider_name}] Aligning {len(tts_results)} audio blocks...")
        tasks = [
            self.generate_subtitles(res.url, res.transcription) for res in tts_results
        ]
        results = await asyncio.gather(*tasks)

        for tts_res, sub_res in zip(tts_results, results):
            reel.blocks[tts_res.id].assets.subtitles = sub_res
