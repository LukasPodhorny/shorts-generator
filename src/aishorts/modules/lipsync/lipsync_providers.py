import asyncio
import os
from urllib.parse import urlparse
from aishorts.modules.avatar import Avatar
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.utils.r2_handler import download_from_url
from aishorts.modules.tts.tts_providers import TTSResult
from aishorts.modules.script.script import Reel, AssetType
from aishorts.utils.pydantic_helper import find_by
from dataclasses import dataclass
from aishorts.modules.provider import Provider
from abc import abstractmethod


@dataclass(order=True)
class LipsyncResult:
    id: int
    filepath: str | None = None
    url: str | None = None
    avatar: Avatar | None = None


class LipsyncProvider(Provider):
    OUTPUT_DIR = os.getenv("LIPSYNC_OUTPUT_DIR") or "output/lipsync"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def populate_reel(self, reel: Reel, **kwargs) -> None:
        pass


class FLOATLipsync(EndpointCaller, LipsyncProvider):
    provider_name = "float"

    def __init__(
        self,
        avatars: list[Avatar],
        download_results: bool = True,
        timeout=2000,
        endpoint_id: str | None = None,
        lipsync_float_api_key: str | None = None,
        **kwargs,
    ):
        self.endpoint_id = endpoint_id or os.getenv("FLOAT_ENDPOINT_ID")
        super().__init__(
            endpoint_id=self.endpoint_id, timeout=timeout, api_key=lipsync_float_api_key
        )
        self.avatars = avatars
        self.download_results = download_results

    def _prepare_single_input(
        self, audio_url: str, emotion: str, seed: int, id: int
    ) -> dict:
        avatar = self.avatars[0]
        face_url = self._extract_url(avatar.face_url)

        return {
            "input": {
                "avatars": {
                    avatar.name: {
                        "avatar_image": face_url,
                        "seed": seed,
                        "a_cfg_scale": avatar.a_cfg_scale,
                        "e_cfg_scale": avatar.e_cfg_scale,
                    }
                },
                "dialogues": [
                    {
                        "avatar": avatar.name,
                        "audio_url": audio_url,
                        "emotion": emotion,
                        "id": id,
                    }
                ],
            }
        }

    @staticmethod
    def _extract_url(url) -> str | None:
        """Extract a plain URL string from a str or dict."""
        if isinstance(url, dict):
            return url.get("url")
        return url

    def _prepare_list_input(
        self, tts_results: list[TTSResult], emotion: str, seed: int
    ) -> dict:
        avatars_dict = {}
        for avatar in self.avatars:
            face_url = self._extract_url(avatar.face_url)

            avatars_dict[avatar.name] = {
                "avatar_image": face_url,
                "seed": seed,
                "a_cfg_scale": avatar.a_cfg_scale,
                "e_cfg_scale": avatar.e_cfg_scale,
            }

        return {
            "input": {
                "avatars": avatars_dict,
                "dialogues": [
                    {
                        "avatar": result.avatar.name,
                        "audio_url": self._extract_url(result.url),
                        "emotion": emotion,
                        "id": result.id,
                    }
                    for result in tts_results
                ],
            }
        }

    async def generate_lipsync(
        self,
        audio_url: str,
        id: int = 0,
        emotion: str = "neutral",
        seed: int = 15,
    ) -> LipsyncResult:
        result = await self.run_async(
            self._prepare_single_input(
                audio_url,
                emotion,
                seed,
                id,
            )
        )

        result_url = result[0]

        filepath = (
            await download_from_url(result_url, LipsyncProvider.OUTPUT_DIR)
            if self.download_results
            else None
        )
        return LipsyncResult(
            filepath=filepath, url=result_url, avatar=self.avatars[0], id=id
        )

    async def populate_reel(
        self,
        reel: Reel,
        emotion: str = "neutral",
        seed: int = 15,
    ) -> None:
        # Reconstruct TTSResults from Reel
        tts_results = []
        for i, block in enumerate(reel.blocks):
            if AssetType.LIPSYNC in block.valid_assets and block.assets.voice_url:
                # Check if this avatar belongs to this provider
                avatar = find_by(self.avatars, name=block.avatar)
                if avatar and avatar.lipsync_provider.lower() == self.provider_name:
                    tts_results.append(
                        TTSResult(
                            id=i,
                            url=block.assets.voice_url,
                            filepath=block.assets.voice_filepath,
                            avatar=avatar,
                        )
                    )

        if not tts_results:
            return

        input_data = self._prepare_list_input(
            tts_results=tts_results, emotion=emotion, seed=seed
        )

        response = await self.run_async(input_data)

        async def _download_and_assign(item):
            video_url = item.get("video_url")
            if isinstance(video_url, dict):
                video_url = video_url.get("url")
            if not video_url or not isinstance(video_url, str):
                block_id = item.get("id", "?")
                print(
                    f"WARNING: Lipsync returned no video_url for block {block_id}, "
                    f"skipping (will use static face fallback)"
                )
                return
            filepath = (
                await download_from_url(video_url, LipsyncProvider.OUTPUT_DIR)
                if self.download_results
                else None
            )
            block_id = item["id"]
            block = reel.blocks[block_id]
            block.assets.lipsync_filepath = filepath
            block.assets.lipsync_url = video_url

        await asyncio.gather(*[_download_and_assign(item) for item in response])


def populate_reel_static_faces(reel: Reel, avatars: list[Avatar]) -> None:
    for block in reel.blocks:
        if AssetType.STATICFACE in block.valid_assets:
            avatar = find_by(avatars, name=block.avatar)
            if avatar:
                if avatar.static_face_url:
                    block.assets.staticface_url = avatar.static_face_url
                    
                    # Extract URL for path generation if it's a dict
                    url_str = avatar.static_face_url
                    if isinstance(url_str, dict):
                        url_str = url_str.get("url", "")

                    # If we have a URL but no path, generate one in output/static_faces
                    if not avatar.static_face_path:
                        filename = os.path.basename(urlparse(url_str).path) or f"static_{avatar.name}.png"
                        block.assets.staticface_filepath = os.path.join("output/static_faces", filename)
                    else:
                        block.assets.staticface_filepath = avatar.static_face_path
                elif avatar.static_face_path:
                    # Fallback for local-only
                    block.assets.staticface_filepath = avatar.static_face_path
                elif avatar.face_url:
                    # No dedicated static face (e.g. cat avatars) — reuse the regular face image
                    block.assets.staticface_url = avatar.face_url
                    url_str = avatar.face_url
                    if isinstance(url_str, dict):
                        url_str = url_str.get("url", "")
                    filename = os.path.basename(urlparse(url_str).path) or f"static_{avatar.name}.png"
                    block.assets.staticface_filepath = os.path.join("output/static_faces", filename)


"""

# currently unavailable
@register_lipsync("wav2lip")
class Wav2LipLipsync(EndpointCaller, LipsyncProvider):

    def __init__(
        self,
        avatar: Avatar,
        timeout=1000,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("WAV2LIP_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.avatar = avatar

    def _prepare_input(self, audio_url):
        data = {
            "input": {
                "face_url": self.avatar.face_video_url,
                "audio_url": audio_url,
                # this is default parameter
                "pads": [0, 10, 0, 0],
            }
        }
        if self.avatar.pads:
            data["input"]["pads"] = self.avatar.pads

        return data

    async def generate_lipsync(
        self,
        audio_url: str,
    ):
        result = await self.run_async(self._prepare_input(audio_url))
        result_url = result["output_url"]
        filepath = CloudflareR2.download_presigned_file(
            result_url, BaseLipsync.OUTPUT_DIR
        )
        return filepath
"""
