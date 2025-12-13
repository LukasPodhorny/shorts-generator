from aishorts.modules.tts.tts_providers import *
import inspect
import asyncio
from aishorts.modules.script.script import Reel
from aishorts.modules.avatar import Avatar
from aishorts.modules.tts.tts_providers import TTSProvider


class VoiceGenerator:
    """
    Parameters:
        avatars: Avatar
            The avatars configurations that will be used.
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
        provider_classes = set(
            [
                TTSProvider.get(avatar.voice.provider.lower())
                # TTS_PROVIDERS.get(avatar.voice.provider.lower())
                for avatar in self.avatars
            ]
        )

        self.provider_instances = [
            cls(avatars=avatars, **kwargs) for cls in provider_classes
        ]

    async def generate_voice(self, text: str, id: int = 0, **kwargs) -> str:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """

        func = self.provider_instances[0].generate_voice
        if inspect.iscoroutinefunction(func):
            return await func(text, id, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return await asyncio.to_thread(func, text, id, **kwargs)

    async def generate_reel_dialogues(self, reel: Reel, **kwargs) -> list[TTSResult]:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """

        tts_results = []
        for tts in self.provider_instances:
            func = tts.generate_reel_dialogues

            if inspect.iscoroutinefunction(func):
                result = await func(reel, **kwargs)
            else:
                print("Running sync TTS in thread...")
                result = await asyncio.to_thread(func, reel, **kwargs)

            tts_results.extend(result)

        tts_results.sort()
        return tts_results
