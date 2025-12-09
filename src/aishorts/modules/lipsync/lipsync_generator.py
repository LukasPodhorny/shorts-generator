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

    def __init__(self, avatars: list[Avatar], **kwargs):

        self.avatars = avatars
        provider_classes = set(
            [
                LIPSYNC_PROVIDERS.get(avatar.lipsync_provider.lower())
                for avatar in self.avatars
            ]
        )

        self.avatars = avatars

        self.provider_instances = [
            cls(avatars=avatars, **kwargs) for cls in provider_classes
        ]

        """
        cls = LIPSYNC_PROVIDERS.get(provider)
        if not cls:
            raise ValueError(f"Unknown Lipsync provider '{provider}'")

        self.tts = cls(avatar=self.avatar, **kwargs)
        """

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
        if inspect.iscoroutinefunction(func):
            return await func(audio_url, id, **kwargs)
        else:
            print("Running sync TTS in thread...")
            return await asyncio.to_thread(func, audio_url, id, **kwargs)

    async def generate_lipsyncs(
        self, tts_results: list[TTSResult], **kwargs
    ) -> list[LipsyncResult]:
        """
        Parameters:
            audio_url: str
                Link with audio file
            emotion: str
                Used by FLOAT backend only.
            seed: int
                Used by FLOAT backend only.
        """

        lipsync_results = []
        for lipsync in self.provider_instances:
            func = lipsync.generate_lipsyncs
            if inspect.iscoroutinefunction(func):
                result = await func(tts_results, **kwargs)
            else:
                print("Running sync TTS in thread...")
                result = await asyncio.to_thread(func, tts_results, **kwargs)

            lipsync_results.extend(result)

        return lipsync_results
