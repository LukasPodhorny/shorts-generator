import asyncio
from aishorts.modules.motion_graphic.base import MotionGraphicRenderer, RenderConfig
from aishorts.modules.motion_graphic.questions import MotionGraphicQuestion


async def main():
    graphic = MotionGraphicQuestion(
        question="What is the capital of France? simet et pet tut montarili",
        answer="PARIS",
    )

    renderer = MotionGraphicRenderer(RenderConfig(output_dir="animated_frames"))
    await renderer.render(graphic, "pop_animation.mov")


if __name__ == "__main__":
    asyncio.run(main())
