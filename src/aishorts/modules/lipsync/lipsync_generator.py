from aishorts.modules.avatar import Avatar
from aishorts.modules.lipsync.lipsync_providers import *
from aishorts.utils.registry import LIPSYNC_PROVIDERS
import inspect
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

    def __init__(self, avatar: Avatar, **kwargs):
        self.avatar = avatar
        provider = self.avatar.lipsync_provider.lower()

        cls = LIPSYNC_PROVIDERS.get(provider)
        if not cls:
            raise ValueError(f"Unknown Lipsync provider '{provider}'")

        self.tts = cls(avatar=self.avatar, **kwargs)

    async def generate_lipsync(self, audio_url: str, **kwargs) -> str:
        """
        Parameters:
            audio_url: str
                Link with audio file
            emotion: str
                Used by FLOAT backend only.
            seed: int
                Used by FLOAT backend only.
            a_cfg_scale: int
                Used by FLOAT backend only.
            e_cfg_scale: int
                Used by FLOAT backend only.
        """
        func = self.tts.generate_lipsync

        if inspect.iscoroutinefunction(func):
            return await func(audio_url=audio_url, **kwargs)
        else:
            print("Running sync Lipsync in thread...")
            return asyncio.to_thread(func, audio_url=audio_url, **kwargs)
