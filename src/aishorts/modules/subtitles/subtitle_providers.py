from openai import AsyncOpenAI
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
import os
from io import BytesIO
from elevenlabs.client import ElevenLabs
from aishorts.utils.registry import register_subtitle_template
import asyncio


class BaseSubtitles:
    def generate_subtitles(self, audio_file: str) -> TranscriptionVerbose:
        raise NotImplementedError("You must implement generate_subtitles function.")


@register_subtitle_template("whisper")
class WhisperSubtitles(BaseSubtitles):

    def __init__(
        self,
        use_lemonfox: bool = True,
        api_key: str | None = None,
    ):
        self.api_key = None
        if use_lemonfox:
            self.api_key = api_key or os.getenv("LEMONFOX_API_KEY")

        self.client = AsyncOpenAI(
            api_key=self.api_key, base_url="https://api.lemonfox.ai/v1"
        )

    async def generate_subtitles(self, audio_file: str):

        with open(audio_file, "rb") as audio:
            transcription = await self.client.audio.transcriptions.create(
                file=audio,
                model="whisper-1",
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        return transcription


@register_subtitle_template("elevenlabs")
class ElevenLabsSubtitles(BaseSubtitles):

    def __init__(
        self,
        display_silence: bool = False,
        min_silence_duration: float = 0.5,
        remove_chars=".,—",
        api_key: str | None = None,
    ):
        self.display_silence = display_silence
        self.min_silence_duration = min_silence_duration
        self.remove_chars = remove_chars
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")

        self.elevenlabs = ElevenLabs(api_key=self.api_key)

    async def generate_subtitles(self, audio_file: str, transcription_text: str):
        with open(audio_file, "rb") as f:
            audio_data = BytesIO(f.read())

        transcription = await asyncio.to_thread(
            self.elevenlabs.forced_alignment.create,
            file=audio_data,
            text=transcription_text,
        )

        transcription_verbose = TranscriptionVerbose(
            duration=transcription.words[-1].end,
            language="english",
            text=transcription_text,
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
                word=subtitle.text.translate({ord(x): "" for x in self.remove_chars}),
            )
            transcription_verbose.words.append(transcription_word)
            prev_word = transcription_word

        return transcription_verbose
