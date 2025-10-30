from avatar import Voice
from avatars_config import AVATARS
from registry import TTS_PROVIDERS


class VoiceGenerator:
    """
    Parameters:
        voice: Voice
            The voice configuration that will be used.
        api_key: str, optional
            Used by F5TTS, LemonFoxTTS backend only.
        endpoint_id: str, optional
            Used by F5TTS backend only.
        timeout: int, optional
            Used by F5TTS backend only.
    """

    def __init__(self, voice: Voice, **kwargs):
        self.voice = voice
        provider = self.voice.provider.lower()

        cls = TTS_PROVIDERS.get(provider)
        if not cls:
            raise ValueError(f"Unknown TTS provider '{provider}'")

        self.tts = cls(voice=self.voice, **kwargs)

    def generate_voice(self, text: str, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """
        return self.tts.generate_voice(text, **kwargs)


if __name__ == "__main__":
    result = VoiceGenerator(AVATARS["biden"].voice).generate_voice(
        "My fellow Americans, this is a test message."
    )
    print(result)
