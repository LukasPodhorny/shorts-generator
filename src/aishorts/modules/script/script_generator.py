import logging
import asyncio
import math
import re
from pydantic import BaseModel, Field
from aishorts.modules.avatar import Avatar
from aishorts.modules.llm.llm_providers import *
from aishorts.modules.llm.llm_providers import LLMProvider
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import DialogueBlock, LatexMedia, ManimMedia, Reel, ReelSeries, SlideMedia, StockVideoMedia, Trigger
from aishorts.modules.llm.llm_generator import LLMGenerator
from aishorts.modules.script.script import BlockType


class MathSlide(SlideMedia):
    trigger: Trigger = Field(default_factory=lambda: Trigger(start_word_index=0, end_word_index=0))


class MathLatex(LatexMedia):
    trigger: Trigger = Field(default_factory=lambda: Trigger(start_word_index=0, end_word_index=0))


class MathScene(BaseModel):
    avatar: str
    text: str
    slide: MathSlide = Field(description="Required teaching or recap slide for this scene, even when a visual is present")
    visual: ManimMedia | MathLatex | None = Field(default=None, description="At most one Manim animation or LaTeX equation")


class MathLesson(BaseModel):
    title: str
    description: str | None = None
    blocks: list[MathScene]


class MathLessonSeries(BaseModel):
    topic: str
    reels: list[MathLesson]

    def to_reel_series(self) -> ReelSeries:
        return ReelSeries(topic=self.topic, reels=[
            Reel(title=reel.title, description=reel.description, blocks=[
                DialogueBlock(type=BlockType.DIALOGUE, avatar=scene.avatar, text=scene.text,
                              media=[scene.slide] + ([scene.visual] if scene.visual else []))
                for scene in reel.blocks
            ]) for reel in self.reels
        ])


class ScriptGenerator:
    """
    Parameters:
        avatar: Avatar
            The avatar configuration that will be used.
        api_key: str, optional
            Used by ChatGPT backend only.
        model: str, optional
            Used by ChatGPT backend only.
        max_output_tokens: int, optional
            Used by ChatGPT backend only.
    """

    def _generate_instructions(self, num_reels: int) -> str:
        """
        Build the final instruction block for the LLM.
        This merges:
        - base script JSON rules
        - avatar acting instructions
        - media/latex settings
        """

        def _bool_rule(boolean: bool, enabled_text: str, disabled_text: str):
            if boolean:
                return enabled_text
            else:
                return disabled_text

        # ------------------------------
        # Build avatar instruction text
        # ------------------------------
        avatar_sections = []
        
        for avatar in self.avatars:
            persona = "Professional narrator; use this voice identity without comic role-play." if self.generate_slides or self.require_stock_video else avatar.instructions
            avatar_sections.append(f"- Avatar '{avatar.name}': {persona}")
        avatar_block = "AVATARS:\n" + "\n".join(avatar_sections)

        # ------------------------------
        # Build media settings text
        # ------------------------------
        media_rules = ["MEDIA SETTINGS:"]
        media_rules.extend(
            [
                _bool_rule(
                    self.generate_image,
                    "- Images: ENABLED (you may generate image media objects).",
                    "- Images: DISABLED (never produce image media objects).",
                ),
                _bool_rule(
                    self.generate_latex,
                    "- LaTeX: ENABLED (you may generate latex media objects).",
                    "- LaTeX: DISABLED (never produce latex media objects).",
                ),
                _bool_rule(
                    self.generate_manim,
                    "- Manim: ENABLED (you may generate manim media objects with a prompt describing the animation).",
                    "- Manim: DISABLED (never produce manim media objects).",
                ),
                _bool_rule(self.generate_slides, "- Slides: ENABLED (one structured slide per narration block).",
                           "- Slides: DISABLED (never produce slide media objects)."),
                ("- Stock video: REQUIRED (exactly one stock_video object with concrete search keywords per dialogue block)."
                 if self.require_stock_video else
                 _bool_rule(self.generate_stock_video and self.stock_video_available, "- Stock video: ENABLED (stock_video objects with concrete search keywords).",
                            "- Stock video: DISABLED (never produce stock_video media objects).")),
            ]
        )

        media_block = "\n".join(media_rules)

        # ------------------------------
        # Build allowed block settings
        # ------------------------------
        blocks_rules = ["ALLOWED BLOCKS:"]

        blocks_rules.extend(
            [
                _bool_rule(
                    BlockType.DIALOGUE in self.allowed_blocks,
                    f"- {BlockType.DIALOGUE.value} ENABLED",
                    f"- {BlockType.DIALOGUE.value} DISABLED",
                ),
                _bool_rule(
                    BlockType.QUESTION in self.allowed_blocks,
                    f"- {BlockType.QUESTION.value} ENABLED",
                    f"- {BlockType.QUESTION.value} DISABLED",
                ),
                _bool_rule(
                    BlockType.SONG in self.allowed_blocks,
                    f"- {BlockType.SONG.value} ENABLED (Generate a song with 'style_prompt', 'text', and optional 'media' triggers).",
                    f"- {BlockType.SONG.value} DISABLED",
                ),
            ]
        )

        blocks_block = "\n".join(blocks_rules)

        reel_conf = ["REEL CONFIGURATION:"]
        reel_conf.append(f"- Number of reels to generate: {num_reels}")
        reel_block = "\n".join(reel_conf)

        # ------------------------------
        # Combine everything into final prompt
        # ------------------------------
        instructions = (
            self.base_instructions.strip()
            + "\n\n"
            + avatar_block
            + "\n\n"
            + media_block
            + "\n\n"
            + reel_block
            + "\n\n"
            + blocks_block
        )
        if self.template_description:
            instructions += "\n\nPRESENTATION FORMAT:\n" + self.template_description

        return instructions

    def __init__(
        self,
        base_instructions: str = None,
        avatars: list[Avatar] = None,
        generate_latex: bool = True,
        generate_image: bool = True,
        generate_manim: bool = False,
        provider: str = "chatgpt",
        allowed_blocks: list[BlockType] = None,
        generate_slides: bool = False,
        generate_stock_video: bool = False,
        stock_video_available: bool = True,
        require_stock_video: bool = False,
        slide_render_config=None,
        template_description: str = "",
        **kwargs,
    ):
        self.base_instructions = base_instructions
        self.avatars = avatars
        self.generate_latex = generate_latex
        self.generate_image = generate_image
        self.generate_manim = generate_manim
        self.allowed_blocks = allowed_blocks if allowed_blocks is not None else [BlockType.DIALOGUE]
        self.generate_slides = generate_slides
        self.generate_stock_video = generate_stock_video
        self.stock_video_available = stock_video_available
        self.require_stock_video = require_stock_video
        self.slide_render_config = slide_render_config
        self.template_description = template_description
        self.provider = provider.lower()
        self.logger = logging.getLogger("ShortsGenerator.ScriptGenerator")

        cls = LLMProvider.get(self.provider)
        if cls is None:
            raise ValueError(f"Unknown LLM provider '{self.provider}'")
        self.llm = cls(**kwargs)

    def validate_script(self, series: ReelSeries, num_reels: int | None = None):
        """Validate formal scenes before any paid asset generation starts."""
        if not self.generate_slides and not self.require_stock_video:
            return
        if not series.reels or (num_reels is not None and len(series.reels) != num_reels):
            raise ValueError("Return exactly the requested number of nonempty reels")
        if self.require_stock_video:
            names = {avatar.name for avatar in self.avatars}
            ids = set()
            for reel in series.reels:
                if not 1 <= len(reel.blocks) <= 32:
                    raise ValueError("Each Stock Story video requires 1-32 scenes")
                for block in reel.blocks:
                    if block.type != BlockType.DIALOGUE or block.avatar not in names:
                        raise ValueError("Use only dialogue blocks and supplied avatar names")
                    words = len(block.text.split())
                    if not 1 <= words <= 180:
                        raise ValueError("Each Stock Story narration scene requires 1-180 words")
                    if len(block.media) != 1 or not isinstance(block.media[0], StockVideoMedia):
                        raise ValueError("Each Stock Story scene requires exactly one stock clip")
                    clip = block.media[0]
                    if clip.id in ids:
                        raise ValueError("Every stock clip must have a unique id")
                    ids.add(clip.id)
                    clip.trigger = Trigger(start_word_index=0, end_word_index=words - 1)
            return
        from aishorts.modules.slides.renderer import render_slide
        allowed_media = {name for name, enabled in {
            "slide": self.generate_slides, "image": self.generate_image,
            "latex": self.generate_latex, "manim": self.generate_manim,
            "stock_video": self.generate_stock_video,
        }.items() if enabled}
        names = {avatar.name for avatar in self.avatars}
        ids = set()
        math_mode = self.slide_render_config is not None and self.slide_render_config.mode == "math"
        for reel in series.reels:
            if not 1 <= len(reel.blocks) <= 32:
                raise ValueError("Each formal video requires 1-32 scenes")
            manim_scenes = 0
            manim_positions = []
            list_scenes = 0
            previous_list_scene = False
            for index, block in enumerate(reel.blocks):
                if block.type not in self.allowed_blocks or getattr(block, "avatar", None) not in names:
                    raise ValueError("Use only allowed narration blocks and supplied avatar names")
                words = len(block.text.split())
                slides = [m for m in block.media if isinstance(m, SlideMedia)]
                media_limit = 2 if math_mode else 3
                if len(slides) != 1 or len(block.media) > media_limit:
                    raise ValueError(
                        f"Scene {index + 1} has {len(slides)} slide(s) and {len(block.media)} media items "
                        f"in one dialogue block. Each scene needs exactly one slide and at most "
                        f"{media_limit - 1} additional visual(s). Put each slide in a separate "
                        "dialogue block in reels[].blocks, with its own narration."
                    )
                title_words = 0
                if index == 0 and words:
                    title = slides[0].title.strip()
                    if title:
                        opening = title if title.endswith((".", "!", "?")) else title + "."
                        if not block.text.lstrip().casefold().startswith(opening.casefold()):
                            title_words = len(opening.split())
                            block.text = f"{opening} {block.text.lstrip()}"
                narration_words = words + title_words
                if not 1 <= narration_words <= 180:
                    raise ValueError("Each narration scene requires 1-180 words, including the opening title")
                visuals = []
                for media in block.media:
                    if media.type not in allowed_media:
                        raise ValueError(f"Media type {media.type} is disabled for this template")
                    if media.id in ids:
                        raise ValueError("Every media item must have a unique id")
                    ids.add(media.id)
                    if isinstance(media, SlideMedia):
                        media.trigger = Trigger(start_word_index=0, end_word_index=narration_words - 1)
                    else:
                        visuals.append(media)

                if math_mode:
                    if re.search(r"\bmanim\b", block.text, re.IGNORECASE):
                        raise ValueError("Do not mention Manim in Math narration; explain the mathematical change instead")
                    if len(visuals) > 1:
                        raise ValueError("Math scenes allow one focused supporting visual")
                    visual = visuals[0] if visuals else None
                    if isinstance(visual, ManimMedia) and slides[0].layout in {"bullets", "process"}:
                        recap = slides[0]
                        last_item = recap.items[-1] if recap.items else None
                        item_summary = (f"{last_item.heading}: {last_item.body}" if last_item.body else last_item.heading) if last_item else ""
                        recap.subtitle = (recap.subtitle.strip() or
                                          (item_summary if len(item_summary) <= 180 else last_item.heading) or recap.title)
                        recap.layout = "title"
                        recap.items = []
                    list_scene = slides[0].layout in {"bullets", "process"}
                    if list_scene and previous_list_scene:
                        raise ValueError("Math lessons cannot use list-style slides in consecutive scenes")
                    list_scenes += list_scene
                    previous_list_scene = list_scene
                    if visual:
                        if isinstance(visual, ManimMedia):
                            start, end = visual.trigger.start_word_index, visual.trigger.end_word_index
                            if not words:
                                raise ValueError("Math animation needs spoken narration in its scene")
                            if not 0 <= start <= end < words:
                                original = (start, end)
                                if 0 <= start < words and end >= start:
                                    end = min(end, words - 1, start + 19)
                                else:
                                    span = min(words, 12)
                                    start = (words - span) // 2
                                    end = start + span - 1
                                self.logger.warning(
                                    "Normalized Math animation window in scene %s from %s to %s",
                                    index + 1, original, (start, end),
                                )
                            visual.trigger = Trigger(start_word_index=start + title_words,
                                                     end_word_index=end + title_words)
                            manim_scenes += 1
                            manim_positions.append(index)
                        else:
                            visual.trigger = Trigger(start_word_index=0, end_word_index=narration_words - 1)
                    if self.slide_render_config:
                        has_panel = bool(visuals and not isinstance(visuals[0], ManimMedia))
                        for has_visual in ((False, True) if has_panel else (False,)):
                            config = self.slide_render_config.model_copy(update={"has_visual": has_visual})
                            render_slide(slides[0], config)
                    continue

                if len(visuals) == 2 and narration_words == 1:
                    # A one-word scene has room for a single supporting visual.
                    block.media.remove(visuals.pop())
                if len(visuals) == 1:
                    visuals[0].trigger = Trigger(start_word_index=0, end_word_index=narration_words - 1)
                elif len(visuals) == 2:
                    first, second = sorted(visuals, key=lambda m: m.trigger.start_word_index)
                    left, right = first.trigger, second.trigger
                    if 0 <= left.start_word_index <= left.end_word_index < right.start_word_index <= right.end_word_index < words:
                        split = title_words + right.start_word_index
                    else:
                        # If the suggested changeover is unusable, use script order.
                        first, second = visuals
                        split = narration_words // 2
                    first.trigger = Trigger(start_word_index=0, end_word_index=split - 1)
                    second.trigger = Trigger(start_word_index=split, end_word_index=narration_words - 1)
                if self.slide_render_config:
                    for has_visual in ((False, True) if visuals else (False,)):
                        config = self.slide_render_config.model_copy(update={"has_visual": has_visual})
                        render_slide(slides[0], config)  # measures actual glyphs; no files or network
            if math_mode:
                if self.generate_manim:
                    minimum = min(6, max(1, math.ceil(len(reel.blocks) / 3)))
                    if manim_scenes == 0:
                        raise ValueError("A math video with Manim enabled needs at least one animation scene")
                    if manim_scenes < minimum:
                        raise ValueError(f"Math lessons with {len(reel.blocks)} scenes need at least {minimum} Manim scenes; got {manim_scenes}")
                    if len(reel.blocks) >= 8:
                        gaps = [manim_positions[0], len(reel.blocks) - manim_positions[-1] - 1]
                        gaps.extend(b - a - 1 for a, b in zip(manim_positions, manim_positions[1:]))
                        if max(gaps) > 3:
                            raise ValueError("Spread Math animations across the lesson; avoid more than three static scenes in a row")
                maximum_lists = max(2, len(reel.blocks) // 3)
                if list_scenes > maximum_lists:
                    raise ValueError(f"Math lessons need varied visuals: at most {maximum_lists} list-style slides; got {list_scenes}")

    async def generate_script(
        self,
        num_reels: int = 1,
        files: list[str] | None = None,
        links: list[str] | None = None,
        user_input: str | None = None,
        **kwargs,
    ) -> ReelSeries:
        instructions = self._generate_instructions(num_reels)
        self.logger.info("Script generator instructions:\n%s", instructions)
        self.logger.info(
            "Script generator sources: files=%s links=%s", files, links
        )
        self.logger.info("Script generator user_input:\n%s", user_input)
        func = self.llm.generate_structure

        math_mode = self.slide_render_config is not None and self.slide_render_config.mode == "math"
        attempts = 4 if math_mode else 2 if self.generate_slides or self.require_stock_video else 1
        for attempt in range(attempts):
            try:
                result = await await_or_thread(
                    func, instructions=instructions, files=files, links=links,
                    user_input=user_input,
                    response_schema=MathLessonSeries if math_mode else ReelSeries, **kwargs,
                )
                if math_mode and not isinstance(result, ReelSeries):
                    result = MathLessonSeries.model_validate(result).to_reel_series()
                else:
                    result = ReelSeries.model_validate(result)
                await asyncio.to_thread(self.validate_script, result, num_reels)
                return result
            except ValueError as exc:
                if attempt == attempts - 1:
                    raise
                instructions += (
                    f"\n\nThe previous script failed validation: {exc}. "
                    "Return a corrected complete script."
                )
                if math_mode:
                    instructions += (
                        " For Math, reels[].blocks must have a separate dialogue block for each scene and slide. "
                        "Every block needs avatar, text, and a required slide object; visual is optional. "
                        "A scene with a Manim or LaTeX visual still needs its own slide."
                    )
                if self.generate_slides:
                    instructions += " Shorten slide text if it does not fit."
