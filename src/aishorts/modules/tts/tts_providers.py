import os
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.modules.avatar import Voice
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.utils.registry import register_tts
import aiohttp


class BaseTTS:
    OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR") or "output/tts"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def generate_voice(
        self,
        text: str,
        return_url: bool = True,
    ) -> str:
        raise NotImplementedError("Subclasses must implement generate_voice()")


@register_tts("f5tts")
class F5TTS(EndpointCaller, BaseTTS):

    def __init__(
        self,
        voice: Voice,
        return_url: bool = False,
        timeout=180,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("F5TTS_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.voice = voice
        self.return_url = return_url

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

    async def generate_voice(self, text: str) -> str:
        result = await self.run_async(self._prepare_input(text))
        result_url = result["output_url"]

        filepath = CloudflareR2.download_presigned_file(result_url, BaseTTS.OUTPUT_DIR)

        if self.return_url:
            return filepath, result_url
        else:
            return filepath


@register_tts("lemonfox")
class LemonFoxTTS(BaseTTS):

    def __init__(
        self,
        voice: Voice,
        return_url: bool = False,
        api_key: str | None = None,
    ):
        self.voice = voice
        self.api_key = api_key or os.getenv("LEMONFOX_API_KEY")
        self.return_url = return_url
        self.r2 = CloudflareR2()

    async def generate_voice(self, text: str) -> str:

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

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    audio_bytes = await response.read()

                    filepath = CloudflareR2.get_random_filepath(
                        BaseTTS.OUTPUT_DIR, ".mp3"
                    )
                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)

                    if self.return_url:
                        result_url = self.r2.upload_file(
                            filepath, "lemonfox/" + os.path.basename(filepath)
                        )
                        return filepath, result_url
                    else:
                        return filepath
                else:
                    text = await response.text()
                    raise RuntimeError(f"Error {response.status}: {text}")
