from aishorts.utils.registry import SUBTITLE_PROVIDERS
from aishorts.modules.subtitles.subtitle_providers import *
import inspect


class SubtitleGenerator:
    """
    Parameters:
        display_silence: bool
            only used by ElevenLabsSubtitles backend
        min_silence_duration: float
            only used by ElevenLabsSubtitles backend
        remove_chars: str
            only used by ElevenLabsSubtitles backend
        api_key: str, optional
            Used by WhisperSubtitles, ElevenLabsSubtitles backend only.
    """

    def __init__(self, provider: str = "elevenlabs", **kwargs):
        self.provider = provider.lower()

        cls = SUBTITLE_PROVIDERS.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown Subtitle provider '{provider}'")

        self.subtitle = cls(**kwargs)

    async def generate_subtitles(self, audio_file: str, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
            transcription_text: str
                Transcription text required by elevenlabs forced alignment
            use_lemonfox: bool
                only used by WhisperSubtitles backend
        """
        func = self.subtitle.generate_subtitles

        if inspect.iscoroutinefunction(func):
            return await func(audio_file, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return asyncio.to_thread(func, audio_file, **kwargs)

    async def generate_multiple_subtitles(
        self, tts_results: list[TTSResult], **kwargs
    ) -> list[TranscriptionVerbose]:

        func = self.subtitle.generate_multiple_subtitles

        if inspect.iscoroutinefunction(func):
            return await func(tts_results, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return asyncio.to_thread(func, tts_results, **kwargs)
