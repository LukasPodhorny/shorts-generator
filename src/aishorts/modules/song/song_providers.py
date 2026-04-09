import asyncio
import os
import aiohttp
from dataclasses import dataclass
from aishorts.modules.script.script import Reel, BlockType, AssetType
from aishorts.modules.provider import Provider
from aishorts.utils.r2_handler import (
    CloudflareR2,
    BucketConfiguration,
)
from abc import abstractmethod


@dataclass
class SongResult:
    filepath: str | None = None
    url: str | None = None


class SongProvider(Provider):
    OUTPUT_DIR = os.getenv("SONG_OUTPUT_DIR") or "output/songs"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    async def populate_reel(
        self,
        reel: Reel,
        **kwargs,
    ) -> None:
        pass


class MinimaxSong(SongProvider):
    provider_name = "minimax"

    def __init__(
        self,
        style_prompt: str | None = None,
        minimax_api_key: str | None = None,
        bucket_configuration: BucketConfiguration = BucketConfiguration(),
        **kwargs,
    ):
        self.style_prompt = style_prompt
        self.api_key = minimax_api_key or os.getenv("MINIMAX_API_KEY")
        self.r2 = CloudflareR2(bucket_configuration)

    async def generate_song(self, text: str) -> SongResult:
        url = "https://api.minimax.io/v1/music_generation"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": "music-2.5",
            "prompt": self.style_prompt,
            "lyrics": text,
            "audio_setting": {
                "sample_rate": 44100,
                "bitrate": 256000,
                "format": "mp3",
            },
            "output_format": "url",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"Minimax API Error {response.status}: {text}")

                result = await response.json()

                # Extract URL from response (assuming standard Minimax structure or direct key)
                # Adjusting based on typical Minimax response structure which usually nests data
                audio_url = None
                if (
                    "data" in result
                    and result["data"]
                    and "audio_file" in result["data"]
                ):
                    audio_url = result["data"]["audio_file"]
                elif "url" in result:
                    audio_url = result["url"]
                else:
                    # Fallback/Debug
                    raise RuntimeError(
                        f"Could not find audio URL in response: {result}"
                    )

                # Download the file
                async with session.get(audio_url) as audio_resp:
                    if audio_resp.status != 200:
                        raise RuntimeError(
                            f"Failed to download generated song: {audio_resp.status}"
                        )

                    audio_bytes = await audio_resp.read()

                filepath = CloudflareR2.get_random_filepath(
                    SongProvider.OUTPUT_DIR, ".mp3"
                )
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)

                # Upload to R2
                public_url = self.r2.upload_file(
                    filepath, "songs/" + os.path.basename(filepath)
                )

                return SongResult(filepath=filepath, url=public_url)

    async def populate_reel(self, reel: Reel, **kwargs) -> None:
        song_blocks = [
            block for block in reel.blocks
            if AssetType.SONG in block.valid_assets
        ]

        if not song_blocks:
            return

        async def _gen_song(block):
            result = await self.generate_song(block.text)
            block.assets.song_filepath = result.filepath
            block.assets.song_url = result.url

        await asyncio.gather(*[_gen_song(block) for block in song_blocks])
