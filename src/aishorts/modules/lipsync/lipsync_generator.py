from aishorts.modules.avatar import Avatar
from aishorts.modules.lipsync.lipsync_providers import *
from aishorts.modules.lipsync.lipsync_providers import LipsyncProvider
from aishorts.modules.script.script import Reel, AssetType
from aishorts.utils.async_utils import await_or_thread
import asyncio


class LipsyncGenerator:
    """
    Parameters:
        avatar: Avatar
            The avatar whose voice configuration will be used.
        timeout: int, optional
            Used by FLOAT, Wav2lip backend only.
        endpoint_id: str, optional
            Used by FLOAT, Wav2lip backend only.
        api_key: str, optional
            Used by FLOAT, Wav2lip backend only.
    """

    def __init__(self, avatars: list[Avatar], **kwargs):
        self.avatars = avatars
        provider_classes = set(
            [
                LipsyncProvider.get(avatar.lipsync_provider.lower())
                for avatar in self.avatars
            ]
        )

        self.provider_instances = [
            cls(avatars=avatars, **kwargs) for cls in provider_classes
        ]

    async def generate_lipsync(
        self, audio_url: str, id: int = 0, **kwargs
    ) -> LipsyncResult:
        """
        Parameters:
            audio_url: str
                Link with audio file
            emotion: str
                Used by FLOAT backend only.
            seed: int
                Used by FLOAT backend only.
        """
        func = self.provider_instances[0].generate_lipsync

        return await await_or_thread(func, audio_url, id, **kwargs)

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates lipsyncs and populates the reel.blocks[i].assets fields in-place."""
        tasks = []
        for lipsync in self.provider_instances:
            func = lipsync.populate_reel
            tasks.append(await_or_thread(func, reel, **kwargs))

        await asyncio.gather(*tasks)
        return reel
