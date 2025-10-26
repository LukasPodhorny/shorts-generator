import os
from avatar import Avatar
from avatars import AVATARS
from runpod_caller import EndpointCaller


class VoiceGenerator(EndpointCaller):
    # timeout probably not working, and it's probably in milliseconds, not seconds
    def __init__(self, avatar: Avatar, timeout=180):
        super().__init__(endpoint_id=os.getenv("F5TTS_ENDPOINT_ID"), timeout=timeout)
        self.avatar = avatar

    def _prepare_input(self, gen_text):
        data = {
            "input": {
                "audio_url": self.avatar.voice_sample_url,
                "gen_text": gen_text,
            }
        }
        if self.avatar.voice_sample_transcript:
            data["input"]["ref_text"] = self.avatar.voice_sample_transcript

        return data

    def generate_voice(self, gen_text: str):
        return self.run_sync(self._prepare_input(gen_text))["output_url"]


if __name__ == "__main__":
    voiceGen = VoiceGenerator(AVATARS["biden"])
    result = voiceGen.generate_voice(
        "This is test, my name is Donald Trump and I love mcroyals. Take it or leave it, but we will return cocaine to coca-cola"
    )
    print(result)
