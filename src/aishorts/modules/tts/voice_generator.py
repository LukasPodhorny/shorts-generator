from aishorts.modules.tts.tts_providers import TTSProvider, TTSResult
from aishorts.modules.script.script import Reel, BlockAssets, AssetType
from aishorts.modules.subtitles.subtitle_providers import expand_numbers_for_speech
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

        return await await_or_thread(func, expand_numbers_for_speech(text), id, **kwargs)

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates voiceovers and populates the reel.blocks[i].assets fields in-place.

        Numbers in block.text are spelled out only for the duration of the TTS
        call so the audio pronounces them predictably. The original text
        (digits intact) is restored afterwards so subtitle alignment — which
        runs in the next pipeline stage and re-applies the same expansion
        internally — can map aligned spans back onto the original digit tokens.
        """
        voice_blocks = [
            b for b in reel.blocks if AssetType.VOICE in b.valid_assets
        ]
        originals = [b.text for b in voice_blocks]
        for block, original in zip(voice_blocks, originals):
            block.text = expand_numbers_for_speech(original)

        try:
            tasks = [
                await_or_thread(tts.populate_reel, reel, **kwargs)
                for tts in self.provider_instances
            ]
            await asyncio.gather(*tasks)
        finally:
            for block, original in zip(voice_blocks, originals):
                block.text = original

        return reel
