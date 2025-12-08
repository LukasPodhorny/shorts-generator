import os
from aishorts.modules.avatar import Avatar
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.utils.registry import register_lipsync
from aishorts.modules.tts.tts_providers import TTSResult
from dataclasses import dataclass


@dataclass
class LipsyncResult:
    filepath: str | None = None
    url: str | None = None
    avatar: Avatar | None = None


class BaseLipsync:
    OUTPUT_DIR = os.getenv("LIPSYNC_OUTPUT_DIR") or "output/lipsync"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def generate_lipsync(self, audio_url: str) -> str:
        raise NotImplementedError("Subclasses must implement generate_lipsync()")


@register_lipsync("float")
class FLOATLipsync(EndpointCaller, BaseLipsync):

    def __init__(
        self,
        avatars: list[Avatar],
        download_results: bool = True,
        timeout=360,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("FLOAT_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.avatars = avatars
        self.downoad_results = download_results

    def _prepare_single_input(self, audio_url, emotion, seed):
        data = {
            "input": {
                "avatars": {
                    self.avatars[0].name: {
                        "avatar_image": self.avatars[0].face_url,
                        "seed": seed,
                        "a_cfg_scale": self.avatars[0].a_cfg_scale,
                        "e_cfg_scale": self.avatars[0].e_cfg_scale,
                    }
                },
                "dialogues": [
                    {
                        "avatar": self.avatars[0].name,
                        "audio_url": audio_url,
                        "emotion": emotion,
                    }
                ],
            }
        }
        return data

    def _prepare_list_input(self, tts_results: list[TTSResult], emotion, seed):
        avatars = {}
        for avatar in self.avatars:
            avatars[avatar.name] = {
                "avatar_image": avatar.face_url,
                "seed": seed,
                "a_cfg_scale": avatar.a_cfg_scale,
                "e_cfg_scale": avatar.e_cfg_scale,
            }

        dialogues = []

        for tts_result in tts_results:
            dialogues.append(
                {
                    "avatar": tts_result.avatar.name,
                    "audio_url": tts_result.url,
                    "emotion": emotion,
                }
            )

        result = {"input": {"avatars": avatars, "dialogues": dialogues}}

        return result

    async def generate_lipsync(
        self,
        audio_url: str,
        emotion: str = "neutral",
        seed: int = 15,
    ) -> LipsyncResult:
        result = await self.run_async(
            self._prepare_single_input(
                audio_url,
                emotion,
                seed,
            )
        )

        result_url = result[0]

        filepath = (
            CloudflareR2.download_presigned_file(result_url, BaseLipsync.OUTPUT_DIR)
            if self.downoad_results
            else None
        )
        return LipsyncResult(filepath=filepath, url=result_url, avatar=self.avatars[0])

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
                CloudflareR2.download_presigned_file(video_url, BaseLipsync.OUTPUT_DIR)
                if self.downoad_results
                else None
            )

            results.append(
                LipsyncResult(
                    filepath=filepath, url=video_url, avatar=tts_results[i].avatar
                )
            )

        return results


@register_lipsync("wav2lip")
class Wav2LipLipsync(EndpointCaller, BaseLipsync):

    def __init__(
        self,
        avatar: Avatar,
        timeout=360,
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
