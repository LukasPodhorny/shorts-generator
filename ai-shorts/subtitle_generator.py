from registry import SUBTITLE_PROVIDERS
from subtitle_providers import *


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
        print(SUBTITLE_PROVIDERS)
        if not cls:
            raise ValueError(f"Unknown Subtitle provider '{provider}'")

        self.subtitle = cls(**kwargs)

    def generate_subtitles(self, audio_file: str, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
            transcription_text: str
                Transcription text required by elevenlabs forced alignment
        """
        return self.subtitle.generate_subtitles(audio_file, **kwargs)


if __name__ == "__main__":
    elevenlabs_subtitles = SubtitleGenerator(provider="elevenlabs")
    transcription = "You get to face a lot of shit, young man. You got a long journey ahead of you, cuz you're gonna find out, that while your dad did a lot of shit to you, you're gonna have to make it on your own."
    subtitles = elevenlabs_subtitles.generate_subtitles(
        audio_file="test_files/goggins-10.wav", transcription_text=transcription
    )
    print(subtitles)
