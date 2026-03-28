import os
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.utils.r2_handler import (
    CloudflareR2,
    BucketConfiguration,
    download_from_url,
)
import aiohttp
from dataclasses import dataclass
from aishorts.modules.script.script import Reel
from aishorts.modules.avatar import Avatar
from aishorts.utils.pydantic_helper import find_by
import asyncio
from aishorts.modules.script.script import Reel, AssetType
from aishorts.modules.provider import Provider
from abc import abstractmethod


@dataclass(order=True)
class TTSResult:
    id: int
    filepath: str | None = None
    url: str | None = None
    avatar: Avatar | None = None
    transcription: str | None = None


class TTSProvider(Provider):

    OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR") or "output/tts"
    # asset type
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def populate_reel(
        self,
        reel: Reel,
        **kwargs,
    ) -> None:
        pass


class F5TTS(EndpointCaller, TTSProvider):
    provider_name = "f5tts"

    def __init__(
        self,
        avatars: list[Avatar],
        download_results: bool = True,
        timeout=600,
        endpoint_id: str | None = None,
        tts_f5tts_api_key: str | None = None,
        **kwargs,
    ):
        self.endpoint_id = endpoint_id or os.getenv("F5TTS_ENDPOINT_ID")
        super().__init__(
            endpoint_id=self.endpoint_id, timeout=timeout, api_key=tts_f5tts_api_key
        )
        self.avatars = avatars
        self.download_results = download_results

    def _prepare_text_input(self, text: str, id: int) -> dict:
        avatar = self.avatars[0]
        
        sample_url = avatar.voice.sample_url
        if isinstance(sample_url, dict):
            sample_url = sample_url.get("url")

        voice_data = {
            "voice_reference": sample_url,
        }

        if avatar.voice.sample_transcript:
            voice_data["ref_text"] = avatar.voice.sample_transcript

        return {
            "input": {
                "voices": {avatar.name: voice_data},
                "dialogues": [
                    {
                        "voice": avatar.name,
                        "text": text,
                        "id": id,
                    }
                ],
            }
        }

    def _prepare_reel_input(self, reel: Reel) -> dict:
        # Build voices dict and valid_avatars set in one pass
        voices = {}
        for avatar in self.avatars:
            if avatar.voice.provider.lower() == "f5tts":
                sample_url = avatar.voice.sample_url
                if isinstance(sample_url, dict):
                    sample_url = sample_url.get("url")
                    
                voices[avatar.name] = {
                    "voice_reference": sample_url,
                    "ref_text": avatar.voice.sample_transcript,
                }

        valid_avatars = set(voices.keys())

        # Build dialogues list with enumeration
        dialogues = [
            {
                "voice": block.avatar,
                "text": block.text,
                "id": idx,
            }
            for idx, block in enumerate(reel.blocks)
            if AssetType.VOICE in block.valid_assets and block.avatar in valid_avatars
        ]

        return {"input": {"voices": voices, "dialogues": dialogues}}

    async def generate_voice(self, text: str, id: int = 0) -> TTSResult:
        result = await self.run_async(self._prepare_text_input(text, id))
        result_url = result[0]["audio_url"]

        filepath = (
            await download_from_url(result_url, TTSProvider.OUTPUT_DIR)
            if self.download_results
            else None
        )

        return TTSResult(
            filepath=filepath,
            url=result_url,
            avatar=self.avatars[0],
            id=result[0]["id"],
            transcription=text,
        )

    async def populate_reel(self, reel: Reel) -> None:
        reel_input = self._prepare_reel_input(reel)
        if not reel_input["input"]["dialogues"]:
            return

        results = await self.run_async(reel_input)

        if not isinstance(results, list):
            raise RuntimeError(f"F5TTS worker returned unexpected output: {results}")

        for i, dialogue in enumerate(results):
            if not isinstance(dialogue, dict):
                raise RuntimeError(f"F5TTS worker returned unexpected dialogue format: {dialogue}")
            
            result_url = dialogue["audio_url"]
            filepath = await download_from_url(result_url, TTSProvider.OUTPUT_DIR)

            # Map back to block
            block_id = dialogue["id"]
            block = reel.blocks[block_id]
            block.assets.voice_filepath = filepath
            block.assets.voice_url = result_url


class LemonFoxTTS(TTSProvider):
    provider_name = "lemonfox"

    def __init__(
        self,
        avatars: list[Avatar],
        tts_lemonfox_api_key: str | None = None,
        bucket_configuration: BucketConfiguration = BucketConfiguration(),
        **kwargs,
    ):
        self.avatars = avatars
        self.tts_lemonfox_api_key = tts_lemonfox_api_key or os.getenv(
            "LEMONFOX_API_KEY"
        )
        self.r2 = CloudflareR2(bucket_configuration)

    async def generate_voice(self, text: str, id: int = 0) -> TTSResult:

        url = "https://api.lemonfox.ai/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.tts_lemonfox_api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "input": text,
            "voice": self.avatars[0].voice.voice_id,
            "response_format": "mp3",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    audio_bytes = await response.read()

                    filepath = CloudflareR2.get_random_filepath(
                        TTSProvider.OUTPUT_DIR, ".mp3"
                    )
                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)

                    result_url = self.r2.upload_file(
                        filepath, "lemonfox/" + os.path.basename(filepath)
                    )

                    return TTSResult(
                        filepath=filepath,
                        url=result_url,
                        avatar=self.avatars[0],
                        id=id,
                        transcription=text,
                    )
                else:
                    text = await response.text()
                    raise RuntimeError(f"Error {response.status}: {text}")

    async def populate_reel(self, reel: Reel) -> None:
        url = "https://api.lemonfox.ai/v1/audio/speech"

        headers = {
            "Authorization": self.tts_lemonfox_api_key,
            "Content-Type": "application/json",
        }

        valid_avatars = {
            avatar.name
            for avatar in self.avatars
            if avatar.voice.provider.lower() == "lemonfox"
        }

        async def generate_single_dialogue(block, id: int):
            """Generate audio for a single dialogue block"""
            avatar = find_by(self.avatars, name=block.avatar)
            data = {
                "input": block.text,
                "voice": avatar.voice.voice_id,
                "response_format": "wav",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        audio_bytes = await response.read()
                        filepath = CloudflareR2.get_random_filepath(
                            TTSProvider.OUTPUT_DIR, ".mp3"
                        )

                        with open(filepath, "wb") as f:
                            f.write(audio_bytes)
                        result_url = self.r2.upload_file(
                            filepath, "lemonfox/" + os.path.basename(filepath)
                        )

                        # Populate block directly
                        block.assets.voice_filepath = filepath
                        block.assets.voice_url = result_url

                    else:
                        text = await response.text()
                        raise RuntimeError(f"Error {response.status}: {text}")

        tasks = [
            generate_single_dialogue(block, idx)
            for idx, block in enumerate(reel.blocks)
            if AssetType.VOICE in block.valid_assets and block.avatar in valid_avatars
        ]

        # Execute all tasks concurrently
        await asyncio.gather(*tasks)
