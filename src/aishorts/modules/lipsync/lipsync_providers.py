import os
from aishorts.modules.avatar import Avatar
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.modules.tts.tts_providers import TTSResult
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
    def generate_lipsyncs(
        self, tts_results: list[TTSResult], **kwargs
    ) -> list[LipsyncResult]:
        pass


class FLOATLipsync(EndpointCaller, LipsyncProvider):
    provider_name = "float"

    def __init__(
        self,
        avatars: list[Avatar],
        download_results: bool = True,
        timeout=1000,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("FLOAT_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.avatars = avatars
        self.downoad_results = download_results

    def _prepare_single_input(
        self, audio_url: str, emotion: str, seed: int, id: int
    ) -> dict:
        avatar = self.avatars[0]

        return {
            "input": {
                "avatars": {
                    avatar.name: {
                        "avatar_image": avatar.face_url,
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

    def _prepare_list_input(
        self, tts_results: list[TTSResult], emotion: str, seed: int
    ) -> dict:
        return {
            "input": {
                "avatars": {
                    avatar.name: {
                        "avatar_image": avatar.face_url,
                        "seed": seed,
                        "a_cfg_scale": avatar.a_cfg_scale,
                        "e_cfg_scale": avatar.e_cfg_scale,
                    }
                    for avatar in self.avatars
                },
                "dialogues": [
                    {
                        "avatar": result.avatar.name,
                        "audio_url": result.url,
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
            CloudflareR2.download_presigned_file(result_url, LipsyncProvider.OUTPUT_DIR)
            if self.downoad_results
            else None
        )
        return LipsyncResult(
            filepath=filepath, url=result_url, avatar=self.avatars[0], id=id
        )

    async def generate_lipsyncs(
        self,
        tts_results: list[TTSResult],
        emotion: str = "neutral",
        seed: int = 15,
    ) -> list[LipsyncResult]:
        input_data = self._prepare_list_input(
            tts_results=tts_results, emotion=emotion, seed=seed
        )

        response = await self.run_async(input_data)

        results = []

        for i, item in enumerate(response):
            video_url = item["video_url"]
            filepath = (
                CloudflareR2.download_presigned_file(
                    video_url, LipsyncProvider.OUTPUT_DIR
                )
                if self.downoad_results
                else None
            )

            results.append(
                LipsyncResult(
                    filepath=filepath,
                    url=video_url,
                    avatar=tts_results[i].avatar,
                    id=item["id"],
                )
            )

        return results


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
