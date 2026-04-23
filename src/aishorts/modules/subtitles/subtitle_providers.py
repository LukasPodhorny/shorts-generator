import os
import re
import asyncio
import aiohttp
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Tuple, Union, Optional
from abc import abstractmethod

# Third-party imports
from openai import AsyncOpenAI
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from elevenlabs.client import ElevenLabs
from num2words import num2words
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


def normalize_alignment_text(text: str) -> str:
    """Normalize punctuation that would otherwise collapse adjacent words into one.

    Em-dashes, en-dashes, and ellipses connect words with no whitespace
    (e.g. "chaos—no", "well…that"). Forced aligners return these as a single
    token with a single timestamp, so even if we later strip the glyph the two
    words stay merged (-> "chaosno"). Replacing with ", " makes the aligner
    treat them as two independent words with independent timings.
    """
    return (
        text.replace("—", ", ")
            .replace("–", ", ")
            .replace("…", ", ")
            .replace("...", ", ")
    )


# Thousands-grouped numbers like "50 000" or "2 000 000" — must be recognized
# before plain digit runs so the internal spaces stay inside one integer.
_THOUSANDS_GROUP_RE = re.compile(r"\d{1,3}(?:\s\d{3})+")
# A "display token" is the unit that will appear in the final subtitles:
# either a thousands-grouped number (kept whole) or any run of non-whitespace.
_DISPLAY_TOKEN_RE = re.compile(r"\d{1,3}(?:\s\d{3})+|\S+")
_DIGIT_RUN_RE = re.compile(r"\d+")


def _spell_integer(digits: str) -> List[str]:
    """'2026' -> ['two', 'thousand', 'twenty', 'six']."""
    spoken = num2words(int(digits))
    cleaned = spoken.replace("-", " ").replace(",", " ").lower()
    return [w for w in cleaned.split() if w != "and"]


def _expand_numbers(text: str) -> str:
    """Spell out every digit sequence inside text.

    Handles thousands groups first ('50 000' -> 'fifty thousand') so their
    internal whitespace stays part of a single integer, then any remaining
    plain digit runs ('2026', '9', '11').
    """
    def spell(match):
        digits = match.group().replace(" ", "")
        return " " + " ".join(_spell_integer(digits)) + " "

    text = _THOUSANDS_GROUP_RE.sub(spell, text)
    return _DIGIT_RUN_RE.sub(spell, text)


def _normalize_like_aligner(text: str) -> List[str]:
    """Mirror wav2vec-modal's _normalize_text so we predict its tokenization."""
    text = text.lower()
    text = re.sub(r"[^a-z\'\s]", "", text)
    return text.split()


def _build_alignment_plan(text: str) -> Tuple[str, List[Tuple[str, int]]]:
    """Return (aligner_text, plan).

    aligner_text is what we send to the forced aligner, with digits spelled
    out so the character-only model can tokenize them. plan is a list of
    (display_token, n_aligner_words) pairs — the aligner returns exactly
    sum(n_aligner_words) word spans, and each display_token absorbs that many
    consecutive spans to produce one subtitle word.
    """
    plan: List[Tuple[str, int]] = []
    aligner_words: List[str] = []
    for display_token in _DISPLAY_TOKEN_RE.findall(text):
        words = _normalize_like_aligner(_expand_numbers(display_token))
        if not words:
            continue
        plan.append((display_token, len(words)))
        aligner_words.extend(words)
    return " ".join(aligner_words), plan


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
            if (
                AssetType.SUBTITLES in block.valid_assets
                and block.assets.voice_filepath
            ):
                tts_results.append(
                    TTSResult(
                        id=i,
                        filepath=block.assets.voice_filepath,
                        transcription=block.text,
                    )
                )

        if not tts_results:
            return

        tasks = [
            self.generate_subtitles(res.filepath, res.transcription)
            for res in tts_results
        ]
        results = await asyncio.gather(*tasks)

        for tts_res, sub_res in zip(tts_results, results):
            reel.blocks[tts_res.id].assets.subtitles = sub_res


class ElevenLabsSubtitles(SubtitlesProvider):
    provider_name = "elevenlabs"

    def __init__(
        self,
        display_silence: bool = False,
        min_silence_duration: float = 1,
        remove_chars="—",
        api_key: str | None = None,
        max_concurrent: int = 5,
    ):
        self.display_silence = display_silence
        self.min_silence_duration = min_silence_duration
        self.remove_chars = remove_chars
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.elevenlabs = ElevenLabs(api_key=self.api_key)
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_subtitles(
        self, audio_file: str, transcription_text: str
    ) -> TranscriptionVerbose:
        async with self.semaphore:
            with open(audio_file, "rb") as f:
                audio_data = BytesIO(f.read())

            normalized_text = normalize_alignment_text(transcription_text)

            transcription = await asyncio.to_thread(
                self.elevenlabs.forced_alignment.create,
                file=audio_data,
                text=normalized_text,
            )

            transcription_verbose = TranscriptionVerbose(
                duration=get_wav_length(audio_file),
                language="english",
                text=normalized_text,
                words=[],
            )

            prev_word = None
            for subtitle in transcription.words:
                word = subtitle.text.replace(" ", "")
                if word == "" and not self.display_silence:
                    if prev_word is not None:
                        silence_duration = subtitle.end - subtitle.start
                        if silence_duration < self.min_silence_duration:
                            prev_word.end = subtitle.end
                    continue

                transcription_word = TranscriptionWord(
                    start=subtitle.start,
                    end=subtitle.end,
                    word=subtitle.text.translate(
                        {ord(x): "" for x in self.remove_chars}
                    ),
                )
                transcription_verbose.words.append(transcription_word)
                prev_word = transcription_word

            return transcription_verbose

    async def populate_reel(self, reel: Reel) -> None:
        tts_results = []
        for i, block in enumerate(reel.blocks):
            if (
                AssetType.SUBTITLES in block.valid_assets
                and block.assets.voice_filepath
            ):
                tts_results.append(
                    TTSResult(
                        id=i,
                        filepath=block.assets.voice_filepath,
                        transcription=block.text,
                    )
                )

        if not tts_results:
            return

        tasks = [
            self.generate_subtitles(res.filepath, res.transcription)
            for res in tts_results
        ]
        results = await asyncio.gather(*tasks)

        for tts_res, sub_res in zip(tts_results, results):
            reel.blocks[tts_res.id].assets.subtitles = sub_res


class ModalWav2VecAligner(SubtitlesProvider):
    provider_name = "modal_wav2vec_aligner"

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        batch_endpoint_url: Optional[str] = None,
        modal_api_key: Optional[str] = None,
        r2_provider=None,
        max_concurrent: int = 3,
        min_silence_duration: float = 1,
        **kwargs,
    ):
        """Initialize the Wav2Vec Aligner provider."""
        self.endpoint_url = endpoint_url or os.getenv("MODAL_WAV2VEC_ENDPOINT_URL")
        self.batch_endpoint_url = batch_endpoint_url or os.getenv(
            "MODAL_WAV2VEC_BATCH_ENDPOINT_URL"
        ) or self._derive_batch_url(self.endpoint_url)
        self.modal_api_key = modal_api_key or os.getenv("MODAL_API_KEY")
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.min_silence_duration = min_silence_duration

        # Use existing R2 handler or initialize the standard one
        self.r2 = r2_provider or CloudflareR2()

    @staticmethod
    def _derive_batch_url(single_url: Optional[str]) -> Optional[str]:
        """Modal endpoint URLs follow `...-<method>.modal.run`, so the batch
        endpoint sits at `...-align-batch.modal.run`. Auto-derive when possible
        so callers only need to set the single URL."""
        if not single_url or not single_url.endswith(".modal.run"):
            return None
        return single_url[: -len(".modal.run")] + "-batch.modal.run"

    def _plan_to_words(
        self, plan: List[Tuple[str, int]], segments: List[Dict]
    ) -> List[TranscriptionWord]:
        expected = sum(n for _, n in plan)
        if len(segments) != expected:
            raise ValueError(
                f"Forced aligner returned {len(segments)} spans but plan "
                f"expected {expected}. Alignment drifted — display tokens "
                f"would not map cleanly back onto audio."
            )

        display = []
        cursor = 0
        for token, n in plan:
            span = segments[cursor : cursor + n]
            cursor += n
            display.append(
                {"word": token, "start": span[0]["start"], "end": span[-1]["end"]}
            )

        words = []
        for i, d in enumerate(display):
            end = d["end"]
            if i < len(display) - 1:
                gap = display[i + 1]["start"] - end
                if gap < self.min_silence_duration:
                    end = display[i + 1]["start"]
            words.append(TranscriptionWord(word=d["word"], start=d["start"], end=end))
        return words

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
        self, audio_file: str, text: str, audio_duration: float | None = None
    ) -> TranscriptionVerbose:
        """Alignment logic wrapped to return the expected OpenAI TranscriptionVerbose type.
        
        Args:
            audio_file: URL or path to audio file
            text: Text to align
            audio_duration: Actual audio duration in seconds (if known)
        """
        async with self.semaphore:
            if not self.endpoint_url:
                raise ValueError("MODAL_WAV2VEC_ENDPOINT_URL is not set.")

            audio_url = await self._prepare_audio(audio_file)

            text = normalize_alignment_text(text)
            aligner_text, plan = _build_alignment_plan(text)

            payload = {"audio_url": audio_url, "text": aligner_text}
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
                    segments = result.get("segments", [])
                    words = self._plan_to_words(plan, segments)

        # Use the actual audio duration if provided, otherwise use last word's end time
        # This is important because subtitle duration is used to offset the next block,
        # and using the last word's end time would cause drift if there's silence at the end
        if audio_duration is not None and audio_duration > 0:
            duration = audio_duration
        else:
            duration = segments[-1]["end"] if segments else 0.0

        return TranscriptionVerbose(
            duration=duration,
            language="english",
            text=text,
            words=words,
        )

    async def populate_reel(self, reel: Reel) -> None:
        # One batched call per reel: GPU idle/scaledown dominates cost,
        # so we want exactly one cold-start amortization per reel.
        tts_results = []
        for i, block in enumerate(reel.blocks):
            if (
                AssetType.SUBTITLES in block.valid_assets
                and block.assets.voice_filepath
            ):
                voice_url = block.assets.voice_url
                if isinstance(voice_url, dict):
                    audio_input = voice_url.get("url", block.assets.voice_filepath)
                else:
                    audio_input = (
                        voice_url if voice_url else block.assets.voice_filepath
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

        if not self.batch_endpoint_url:
            raise ValueError(
                "MODAL_WAV2VEC_BATCH_ENDPOINT_URL is not set and could not be "
                "derived from MODAL_WAV2VEC_ENDPOINT_URL."
            )

        print(
            f"[{self.provider_name}] Aligning {len(tts_results)} audio blocks "
            f"in one batched request..."
        )

        async def prep(res: TTSResult):
            url = await self._prepare_audio(res.url)
            duration = None
            if res.filepath and os.path.exists(res.filepath):
                try:
                    duration = get_wav_length(res.filepath)
                except Exception as e:
                    print(
                        f"Warning: Could not get duration for {res.filepath}: {e}"
                    )
            return url, duration

        prepped = await asyncio.gather(*[prep(r) for r in tts_results])

        normalized_texts = [
            normalize_alignment_text(r.transcription) for r in tts_results
        ]
        plans: List[List[Tuple[str, int]]] = []
        aligner_texts: List[str] = []
        for text in normalized_texts:
            aligner_text, plan = _build_alignment_plan(text)
            aligner_texts.append(aligner_text)
            plans.append(plan)

        items = [
            {"audio_url": url, "text": aligner_text}
            for (url, _), aligner_text in zip(prepped, aligner_texts)
        ]
        payload: Dict = {"items": items}
        if self.modal_api_key:
            payload["api_key"] = self.modal_api_key

        async with self.semaphore:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.batch_endpoint_url, json=payload, timeout=600
                ) as response:
                    print(
                        f"[{self.provider_name}] Modal batch responded with "
                        f"status {response.status}"
                    )
                    if not response.ok:
                        err = await response.text()
                        raise Exception(
                            f"Modal Wav2Vec batch alignment failed with "
                            f"{response.status}: {err}"
                        )
                    result = await response.json()

        batch_results = result.get("results", [])
        if len(batch_results) != len(tts_results):
            raise Exception(
                f"Modal batch returned {len(batch_results)} results for "
                f"{len(tts_results)} items"
            )

        for tts_res, (_, duration), single_res, text, plan in zip(
            tts_results, prepped, batch_results, normalized_texts, plans
        ):
            segments = single_res.get("segments", [])
            words = self._plan_to_words(plan, segments)
            if duration is not None and duration > 0:
                final_duration = duration
            else:
                final_duration = segments[-1]["end"] if segments else 0.0
            reel.blocks[tts_res.id].assets.subtitles = TranscriptionVerbose(
                duration=final_duration,
                language="english",
                text=text,
                words=words,
            )
