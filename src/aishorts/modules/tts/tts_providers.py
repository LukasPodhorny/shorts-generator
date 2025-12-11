import os
from aishorts.utils.runpod_caller import EndpointCaller
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.utils.registry import register_tts
import aiohttp
from dataclasses import dataclass
from aishorts.modules.script.script import Reel
from aishorts.modules.avatar import Avatar
from aishorts.utils.pydantic_helper import find_by
import asyncio
from aishorts.modules.script.script import Reel


@dataclass
class TTSResult:
    filepath: str | None = None
    url: str | None = None
    avatar: Avatar | None = None
    id: int | None = None
    transcription: str | None = None


class BaseTTS:
    OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR") or "output/tts"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def generate_voice(
        self,
        text: str,
        id: int = 0,
    ) -> TTSResult:
        raise NotImplementedError("Subclasses must implement generate_voice()")

    def generate_reel_dialogues(
        self,
        reel: Reel,
    ) -> list[TTSResult]:
        raise NotImplementedError("Subclasses must implement generate_reel_dialogues()")


@register_tts("f5tts")
class F5TTS(EndpointCaller, BaseTTS):

    def __init__(
        self,
        avatars: list[Avatar],
        download_results: bool = True,
        timeout=500,
        endpoint_id: str | None = None,
        api_key: str | None = None,
    ):
        self.endpoint_id = endpoint_id or os.getenv("F5TTS_ENDPOINT_ID")
        super().__init__(endpoint_id=self.endpoint_id, timeout=timeout, api_key=api_key)
        self.avatars = avatars
        self.download_results = download_results

    def _prepare_text_input(self, text: str, id: int) -> dict:
        avatar = self.avatars[0]

        voice_data = {
            "voice_reference": avatar.voice.sample_url,
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
        voices = {
            avatar.name: {
                "voice_reference": avatar.voice.sample_url,
                "ref_text": avatar.voice.sample_transcript,
            }
            for avatar in self.avatars
            if avatar.voice.provider.lower() == "f5tts"
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
            if block.type == "dialogue" and block.avatar in valid_avatars
        ]

        return {"input": {"voices": voices, "dialogues": dialogues}}

    async def generate_voice(self, text: str, id: int = 0) -> TTSResult:
        result = await self.run_async(self._prepare_text_input(text, id))
        result_url = result[0]["audio_url"]

        filepath = (
            CloudflareR2.download_presigned_file(result_url, BaseTTS.OUTPUT_DIR)
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

    async def generate_reel_dialogues(self, reel: Reel) -> list[TTSResult]:
        tts_results = []

        reel_input = self._prepare_reel_input(reel)
        results = await self.run_async(reel_input)

        for i, dialogue in enumerate(results):
            result_url = dialogue["audio_url"]
            filepath = CloudflareR2.download_presigned_file(
                result_url, BaseTTS.OUTPUT_DIR
            )

            tts_results.append(
                TTSResult(
                    filepath=filepath,
                    url=result_url,
                    avatar=find_by(
                        self.avatars, name=reel_input["input"]["dialogues"][i]["voice"]
                    ),
                    id=dialogue["id"],
                    transcription=reel_input["input"]["dialogues"][i]["text"],
                )
            )

        return tts_results


@register_tts("lemonfox")
class LemonFoxTTS(BaseTTS):

    def __init__(
        self,
        avatars: list[Avatar],
        api_key: str | None = None,
    ):
        self.avatars = avatars
        self.api_key = api_key or os.getenv("LEMONFOX_API_KEY")
        self.r2 = CloudflareR2()

    async def generate_voice(self, text: str, id: int = 0) -> TTSResult:

        url = "https://api.lemonfox.ai/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                        BaseTTS.OUTPUT_DIR, ".mp3"
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

    async def generate_reel_dialogues(self, reel: Reel) -> list[TTSResult]:
        url = "https://api.lemonfox.ai/v1/audio/speech"

        headers = {
            "Authorization": self.api_key,
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
                        result_url = self.r2.upload_file(
                            filepath, "lemonfox/" + os.path.basename(filepath)
                        )

                        return TTSResult(
                            filepath=filepath,
                            url=result_url,
                            avatar=avatar,
                            id=id,
                            transcription=block.text,
                        )
                    else:
                        text = await response.text()
                        raise RuntimeError(f"Error {response.status}: {text}")

        tasks = [
            generate_single_dialogue(block, idx)
            for idx, block in enumerate(reel.blocks)
            if block.type == "dialogue" and block.avatar in valid_avatars
        ]

        # Execute all tasks concurrently
        return await asyncio.gather(*tasks)
