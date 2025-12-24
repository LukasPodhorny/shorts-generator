from aishorts.modules.tts.tts_providers import TTSProvider, TTSResult
from aishorts.modules.script.script import Reel
from aishorts.modules.avatar import Avatar
from aishorts.utils.async_utils import await_or_thread
import asyncio


class VoiceGenerator:
    """
    Parameters:
        avatars: Avatar
            The avatars configurations that will be used.
        download_results: bool, optional
            Whether to download the generated audio files locally.
        tts_f5tts_api_key: str, optional
            API key for F5TTS provider.
        tts_lemonfox_api_key: str, optional
            API key for LemonFox provider.

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

    async def generate_voice(self, text: str, id: int = 0, **kwargs) -> TTSResult:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """

        func = self.provider_instances[0].generate_voice

        return await await_or_thread(func, text, id, **kwargs)

    async def generate_reel_dialogues(self, reel: Reel, **kwargs) -> list[TTSResult]:
        """
        Parameters:
            text: str
                Text that will be converted to speech
        """

        tts_results = []
        tasks = []
        for tts in self.provider_instances:
            func = tts.generate_reel_dialogues
            tasks.append(await_or_thread(func, reel, **kwargs))

        results = await asyncio.gather(*tasks)
        for res in results:
            tts_results.extend(res)

        tts_results.sort()
        return tts_results
