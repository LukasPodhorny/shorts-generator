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


async def main():
    elevenlabs_subtitles = SubtitleGenerator(provider="elevenlabs")
    transcription = "You get to face a lot of shit, young man. You got a long journey ahead of you, cuz you're gonna find out, that while your dad did a lot of shit to you, you're gonna have to make it on your own."
    subtitles = await elevenlabs_subtitles.generate_subtitles(
        audio_file="test_files/goggins-10.wav", transcription_text=transcription
    )
    print(subtitles)


if __name__ == "__main__":
    asyncio.run(main())
