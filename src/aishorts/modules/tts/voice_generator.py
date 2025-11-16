from aishorts.modules.avatar import Voice
from aishorts.modules.tts.tts_providers import *
from aishorts.utils.registry import TTS_PROVIDERS
import inspect
import asyncio


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

    async def generate_voice(self, text: str, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """
        func = self.tts.generate_voice

        if inspect.iscoroutinefunction(func):
            return await func(text, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return asyncio.to_thread(func, text, **kwargs)
