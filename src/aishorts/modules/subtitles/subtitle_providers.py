from openai import AsyncOpenAI
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
import os
from io import BytesIO
from elevenlabs.client import ElevenLabs
import asyncio
from aishorts.modules.tts.tts_providers import TTSResult
from aishorts.modules.provider import Provider
from aishorts.modules.provider import Provider, AssetType
from abc import abstractmethod
from pydub import AudioSegment
from aishorts.modules.script.script import Reel


class SubtitlesProvider(Provider):
    @abstractmethod
    def generate_multiple_subtitles(
    def populate_reel(
        self,
        tts_results: list[TTSResult],
        reel: Reel,
        **kwargs,
    ) -> list[TranscriptionVerbose]:
    ) -> None:
        pass


def get_wav_length(path: str):
    audio = AudioSegment.from_wav(path)
    duration = len(audio) / 1000.0

    return duration


class WhisperSubtitles(SubtitlesProvider):
    provider_name = "whisper"

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

    async def generate_subtitles(self, audio_file: str) -> TranscriptionVerbose:

        with open(audio_file, "rb") as audio:
            transcription = await self.client.audio.transcriptions.create(
                file=audio,
                model="whisper-1",
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        return transcription


class ElevenLabsSubtitles(SubtitlesProvider):
    provider_name = "elevenlabs"

    def __init__(
        self,
        display_silence: bool = False,
        min_silence_duration: float = 0.5,
        remove_chars="—",
        api_key: str | None = None,
    ):
        self.display_silence = display_silence
        self.min_silence_duration = min_silence_duration
        self.remove_chars = remove_chars
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")

        self.elevenlabs = ElevenLabs(api_key=self.api_key)

    async def generate_subtitles(
        self, audio_file: str, transcription_text: str
    ) -> TranscriptionVerbose:
        with open(audio_file, "rb") as f:
            audio_data = BytesIO(f.read())

        transcription = await asyncio.to_thread(
            self.elevenlabs.forced_alignment.create,
            file=audio_data,
            text=transcription_text,
        )

        transcription_verbose = TranscriptionVerbose(
            duration=get_wav_length(audio_file),
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

    async def generate_multiple_subtitles(
        self, tts_results: list[TTSResult]
    ) -> list[TranscriptionVerbose]:
    async def populate_reel(
        self, reel: Reel
    ) -> None:
        
        tts_results = []
        for i, block in enumerate(reel.blocks):
            if AssetType.SUBTITLES in block.valid_assets and block.assets.voice_filepath:
                tts_results.append(TTSResult(
                    id=i,
                    filepath=block.assets.voice_filepath,
                    transcription=block.text
                ))

        tasks = [
            self.generate_subtitles(tts_result.filepath, tts_result.transcription)
            for tts_result in tts_results
        ]
        return await asyncio.gather(*tasks)
        results = await asyncio.gather(*tasks)
        
        for tts_res, sub_res in zip(tts_results, results):
            reel.blocks[tts_res.id].assets.subtitles = sub_res
