import os
import requests
from runpod_caller import EndpointCaller
from avatar import Voice
from r2_handler import CloudflareR2
from registry import register_tts


class BaseTTS:
    OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR") or "output/tts"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def generate_voice(self, text: str) -> str:
        raise NotImplementedError("Subclasses must implement generate_voice()")


@register_tts("f5tts")
class F5TTS(EndpointCaller, BaseTTS):

    def __init__(
        self,
        voice: Voice,
        timeout=180,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("F5TTS_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.voice = voice

    def _prepare_input(self, text: str):
        data = {
            "input": {
                "audio_url": self.voice.sample_url,
                "gen_text": text,
            }
        }
        if self.voice.sample_transcript:
            data["input"]["ref_text"] = self.voice.sample_transcript
        return data

    def generate_voice(self, text: str) -> str:
        result_url = self.run_sync(self._prepare_input(text))["output_url"]
        filepath = CloudflareR2.download_presigned_file(result_url, BaseTTS.OUTPUT_DIR)
        return filepath


@register_tts("lemonfox")
class LemonFoxTTS(BaseTTS):

    def __init__(self, voice: Voice, api_key: str | None = None):
        self.voice = voice
        self.api_key = api_key or os.getenv("LEMONFOX_API_KEY")

    def generate_voice(self, text: str) -> str:

        url = "https://api.lemonfox.ai/v1/audio/speech"
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }
        data = {
            "input": text,
            "voice": self.voice.voice_id,
            "response_format": "mp3",
        }

        response = requests.post(
            url,
            headers=headers,
            json=data,
        )

        if response.status_code == 200:
            filepath = CloudflareR2.get_random_filepath(BaseTTS.OUTPUT_DIR, ".mp3")
            with open(filepath, "wb") as f:
                f.write(response.content)

            return filepath
        else:
            raise RuntimeError(f"Error {response.status_code}: {response.text}")
