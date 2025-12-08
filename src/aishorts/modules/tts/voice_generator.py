from aishorts.modules.avatar import Voice
from aishorts.modules.tts.tts_providers import *
from aishorts.utils.registry import TTS_PROVIDERS
import inspect
import asyncio
from aishorts.modules.script.script import Reel
from aishorts.modules.avatar import Avatar


class VoiceGenerator:
    """
    Parameters:
        avatar: Avatar
            The avatar configuration that will be used.
        download_results: bool, optional
            Whether to download the generated audio files locally.
        api_key: str, optional
            Used by F5TTS, LemonFoxTTS backend only.
        endpoint_id: str, optional
            Used by F5TTS backend only.
        timeout: int, optional
            Used by F5TTS backend only.

    One reel needs to have same provider for all dialogues.
    """

    def __init__(self, avatars: list[Avatar], **kwargs):
        self.avatars = avatars
        provider = self.avatars[0].voice.provider.lower()

        cls = TTS_PROVIDERS.get(provider)
        if not cls:
            raise ValueError(f"Unknown TTS provider '{provider}'")

        self.tts = cls(avatars=avatars, **kwargs)

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

    async def generate_reel_dialogues(self, reel: Reel, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """
        func = self.tts.generate_reel_dialogues

        if inspect.iscoroutinefunction(func):
            return await func(reel, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return asyncio.to_thread(func, reel, **kwargs)
