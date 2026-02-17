from aishorts.modules.provider import Provider
from abc import abstractmethod
import os
from aishorts.modules.script.script import Reel
from aishorts.modules.motion_graphic.motion_graphic import (
    MotionGraphic,
    MotionGraphicRenderer,
)
from typing import Type
import uuid
from pydub import AudioSegment
import asyncio


class QuestionProvider(Provider):
    OUTPUT_DIR = os.getenv("QUESTION_OUTPUT_DIR") or "output/question"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    async def populate_reel(self, reel: Reel, **kwargs) -> None:
        pass


class MotionGraphicQuestionProvider(QuestionProvider):
    provider_name = "motion_graphic"

    def __init__(
        self,
        graphic_class: Type[MotionGraphic],
        renderer: MotionGraphicRenderer | None = None,
        typing_duration: float = 3.0,
        thinking_duration: float = 5.0,
        answer_duration: float = 2.0,
    ):
        self.graphic_class = graphic_class
        self.renderer = renderer or MotionGraphicRenderer()
        self.typing_duration = typing_duration
        self.thinking_duration = thinking_duration
        self.answer_duration = answer_duration

    async def populate_reel(self, reel: Reel, **kwargs) -> None:
        for block in reel.blocks:
            if block.type == "question":

                typing_duration = self.typing_duration

                # If voiceover exists, sync typing duration to audio length
                if block.assets.voice_filepath and os.path.exists(
                    block.assets.voice_filepath
                ):
                    try:
                        audio = await asyncio.to_thread(
                            AudioSegment.from_file, block.assets.voice_filepath
                        )
                        typing_duration = len(audio) / 1000.0
                    except Exception as e:
                        print(f"Failed to get audio duration for question block: {e}")

                graphic = self.graphic_class(
                    question=block.text,
                    answer=block.answer,
                    typing_duration=typing_duration,
                    thinking_duration=self.thinking_duration,
                    answer_duration=self.answer_duration,
                )

                filename = f"{uuid.uuid4()}.mov"
                output_path = os.path.join(self.OUTPUT_DIR, filename)

                await self.renderer.render(graphic, output_path)

                block.assets.question_filepath = output_path
