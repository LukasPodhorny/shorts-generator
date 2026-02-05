from aishorts.modules.tts.tts_providers import TTSProvider, TTSResult
from aishorts.modules.script.script import Reel, BlockAssets, AssetType
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

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates voiceovers and populates the reel.blocks[i].assets fields in-place."""
        tasks = []
        for tts in self.provider_instances:
            func = tts.populate_reel
            tasks.append(await_or_thread(func, reel, **kwargs))

        await asyncio.gather(*tasks)

        return reel
