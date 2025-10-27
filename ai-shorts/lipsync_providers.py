import os
from avatar import Avatar
from avatars import AVATARS
from runpod_caller import EndpointCaller


class BaseLipsync:
    def generate_lipsync(self, audio_url: str) -> str:
        raise NotImplementedError("Subclasses must implement generate_lipsync()")


class FLOATLipsync(EndpointCaller, BaseLipsync):
    def __init__(
        self,
        avatar: Avatar,
        timeout=360,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("FLOAT_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.avatar = avatar

    def _prepare_input(self, audio_url, emotion, seed, a_cfg_scale, e_cfg_scale):
        data = {
            "input": {
                "face_url": self.avatar.face_url,
                "audio_url": audio_url,
                "emotion": emotion,
                "seed": seed,
                "a_cfg_scale": a_cfg_scale,
                "e_cfg_scale": e_cfg_scale,
            }
        }
        return data

    def generate_lipsync(
        self,
        audio_url: str,
        emotion: str = "neutral",
        seed: int = 15,
        a_cfg_scale: int = 2,
        e_cfg_scale: int = 1,
    ):
        return self.run_sync(
            self._prepare_input(audio_url, emotion, seed, a_cfg_scale, e_cfg_scale)
        )["output_url"]


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

    def generate_lipsync(
        self,
        audio_url: str,
    ):
        return self.run_sync(self._prepare_input(audio_url))["output_url"]
