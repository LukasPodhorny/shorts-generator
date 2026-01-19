from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
from aishorts.modules.script.script import Reel
from aishorts.modules.motion_graphic.base import MotionGraphic, MotionGraphicRenderer
from typing import Type
import uuid


@dataclass
class QuestionResult:
    media: MediaFile
    duration: float | None = None


class QuestionProvider(Provider):
    OUTPUT_DIR = os.getenv("QUESTION_OUTPUT_DIR") or "output/question"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    async def get_reel_questions(self, reel: Reel, **kwargs) -> list[QuestionResult]:
        pass


class MotionGraphicQuestionProvider(QuestionProvider):
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

    async def get_reel_questions(self, reel: Reel, **kwargs) -> list[QuestionResult]:
        results = []

        for block in reel.blocks:
            if block.type == "question":
                graphic = self.graphic_class(
                    question=block.question,
                    answer=block.answer,
                    typing_duration=self.typing_duration,
                    thinking_duration=self.thinking_duration,
                    answer_duration=self.answer_duration,
                )

                filename = f"{uuid.uuid4()}.mov"
                output_path = os.path.join(self.OUTPUT_DIR, filename)

                await self.renderer.render(graphic, output_path)

                results.append(
                    QuestionResult(
                        media=MediaFile(path=output_path),
                        duration=graphic.get_total_duration(),
                    )
                )

        return results
