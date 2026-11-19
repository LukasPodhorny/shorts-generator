import logging
import asyncio
from aishorts.modules.avatar import Avatar
from aishorts.modules.llm.llm_providers import *
from aishorts.modules.llm.llm_providers import LLMProvider
from aishorts.utils.async_utils import await_or_thread
from aishorts.modules.script.script import ReelSeries, SlideMedia, Trigger
from aishorts.modules.llm.llm_generator import LLMGenerator
from aishorts.modules.script.script import BlockType


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
            persona = "Professional narrator; use this voice identity without comic role-play." if self.generate_slides else avatar.instructions
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
                _bool_rule(self.generate_stock_video and self.stock_video_available, "- Stock video: ENABLED (stock_video objects with concrete search keywords).",
                           "- Stock video: DISABLED (never produce stock_video media objects)."),
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
        if not self.generate_slides:
            return
        from aishorts.modules.slides.renderer import render_slide

        if not series.reels or (num_reels is not None and len(series.reels) != num_reels):
            raise ValueError("Return exactly the requested number of nonempty reels")
        allowed_media = {name for name, enabled in {
            "slide": self.generate_slides, "image": self.generate_image,
            "latex": self.generate_latex, "manim": self.generate_manim,
            "stock_video": self.generate_stock_video,
        }.items() if enabled}
        names = {avatar.name for avatar in self.avatars}
        ids = set()
        for reel in series.reels:
            if not 1 <= len(reel.blocks) <= 32:
                raise ValueError("Each formal video requires 1-32 scenes")
            for index, block in enumerate(reel.blocks):
                if block.type not in self.allowed_blocks or getattr(block, "avatar", None) not in names:
                    raise ValueError("Use only allowed narration blocks and supplied avatar names")
                words = len(block.text.split())
                slides = [m for m in block.media if isinstance(m, SlideMedia)]
                if len(slides) != 1 or len(block.media) > 3:
                    raise ValueError("Each scene needs exactly one slide and at most two additional visuals")
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

        attempts = 2 if self.generate_slides else 1
        for attempt in range(attempts):
            try:
                result = await await_or_thread(
                    func, instructions=instructions, files=files, links=links,
                    user_input=user_input, response_schema=ReelSeries, **kwargs,
                )
                result = ReelSeries.model_validate(result)
                await asyncio.to_thread(self.validate_script, result, num_reels)
                return result
            except ValueError as exc:
                if attempt == attempts - 1:
                    raise
                instructions += (
                    f"\n\nThe previous script failed validation: {exc}. "
                    "Return a corrected complete script. Shorten slide text if it does not fit."
                )
