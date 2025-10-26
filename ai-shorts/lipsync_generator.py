import os
from avatar import Avatar
from avatars import AVATARS
from runpod_caller import EndpointCaller


class LipsyncGenerator(EndpointCaller):
    def __init__(self, avatar: Avatar, timeout=360):
        super().__init__(endpoint_id=os.getenv("FLOAT_ENDPOINT_ID"), timeout=timeout)
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


if __name__ == "__main__":
    lipsyncGen = LipsyncGenerator(AVATARS["biden"])
    result = lipsyncGen.generate_lipsync("https://files.catbox.moe/r234pd.wav")
    print(result)
