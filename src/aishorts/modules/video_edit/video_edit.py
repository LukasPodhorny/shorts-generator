from dataclasses import dataclass, field
import os
import logging
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
import subprocess
from pydantic import BaseModel, Field
import uuid
from aishorts.modules.provider import Provider
from abc import abstractmethod
from typing import List, Union, Dict, Optional, Any
from pathlib import Path
from aishorts.utils.image_utils import ImageStyle
from aishorts.modules.script.script import Reel, Block, AssetType

logger = logging.getLogger(__name__)


def resolve_media_url(url: Union[str, dict, None]) -> Optional[dict]:
    """Normalize a str|dict URL into the dict form FilterGraph.add_input expects.

    A bare URL string would otherwise be wrapped in a Path by add_input, so URLs
    must be passed as dicts. Local paths are passed through unchanged elsewhere.
    """
    if not url:
        return None
    return url if isinstance(url, dict) else {"url": url}


@dataclass
class MediaTiming:
    """Represents the absolute timing for a media element (image or latex)"""

    filepath: str
    start_time: float
    end_time: float
    media_type: str
    url: Optional[Union[str, dict]] = None


@dataclass
class FFmpegCommand:
    """
    FFmpeg command with ordered inputs.
    The command references inputs by their index [0], [1], [2], etc.
    """

    # The actual inputs in order - these get replaced by provider
    inputs: List[Union[Path, str, dict]]

    # The filter graph and other args (already have correct indices)
    args: List[str]

    # Video codec for optimatization
    video_codec: Optional[str] = None

    # Optional: metadata about what each input is (for debugging/logging)
    input_labels: List[str] = field(default_factory=list)

    def to_command_list(self, resolved_inputs: List[str]) -> List[str]:
        """
        Build final FFmpeg command with resolved input paths/URLs

        Args:
            resolved_inputs: List of paths/URLs in same order as self.inputs
        """
        cmd = ["ffmpeg"]

        # Add all inputs
        for input_path in resolved_inputs:
            cmd.extend(["-i", str(input_path)])

        # Add the rest of the arguments
        cmd.extend(self.args)

        # Add video codec
        if self.video_codec:
            cmd.extend(["-c:v", self.video_codec])

        return cmd


class SubtitleStyle(BaseModel):
    font: str = "Poppins"
    font_size: int = 250
    color: str = "&H00FFFFFF"
    secondary_color: str = "&H00EDDC40"
    stroke_width: int = 12
    stroke_color: str = "&H00000000"
    shadow_color: str = "&H64000000"
    boldness: int = 0
    letter_spacing: int = 0
    shadow_offset: int = 5
    alignment: int = 5
    offset_y: int = 100
    max_chars_per_line: int = 1
    break_characters: str = ".!?;:"
    remove_chars: str = ".,;"
    karaoke_enabled: bool = False


class TemplateConfig(BaseModel):
    bg_video: Union[str, dict, None] = None
    music: Union[str, dict, None] = None
    subtitle_style: Optional[SubtitleStyle] = Field(default_factory=SubtitleStyle)
    chromakey_color: Optional[str] = "0x00FF00"
    chromakey_similarity: Optional[float] = 0.17
    chromakey_blend: Optional[float] = 0.2
    image_style: Optional[ImageStyle] = Field(default_factory=ImageStyle)
    max_image_width: Optional[int] = 800
    max_image_height: Optional[int] = 600
    latex_style: Optional[ImageStyle] = Field(default_factory=ImageStyle)
    latex_width: Optional[int] = 600
    latex_height: Optional[int] = 300
    manim_width: Optional[int] = 1000
    manim_style: Optional[ImageStyle] = Field(
        default_factory=lambda: ImageStyle(corner_radius=40)
    )
    question_graphic: str = "MotionGraphicQuestion"
    style_prompt: str = "pop music, Female vocals"

    def get_question_graphic_class(self):
        from aishorts.modules.motion_graphic.questions import BasicQuestion

        registry = {
            "MotionGraphicQuestion": BasicQuestion,
        }

        if self.question_graphic not in registry:
            raise ValueError(f"Unknown motion graphic class: {self.question_graphic}")

        return registry[self.question_graphic]


class VideoTemplate(BaseModel):
    edit_template: str
    template_config: TemplateConfig


class AssSubtitles:
    def __init__(self, data: str):
        self.data = data

    def download(self):
        subs_path = f"/tmp/{uuid.uuid4()}.ass"
        with open(subs_path, "w", encoding="utf-8") as f:
            f.write(self.data)

        return subs_path


class EditTemplate(Provider):

    OUTPUT_DIR = os.getenv("VIDEO_OUTPUT_DIR") or "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Assets that are always generated for this template (hidden from users).
    core_assets: List[AssetType] = []
    # User-toggleable tags mapped to their default enabled state.
    tag_assets: Dict[AssetType, bool] = {}
    # Block types this template can render.
    allowed_blocks: List[Any] = []
    # Easing used for the media overlay fade in/out (slide is always quart).
    media_fade_easing: str = "linear"

    @classmethod
    def resolve_required_assets(
        cls, enabled_tags: Optional[List[str]]
    ) -> List[AssetType]:
        if enabled_tags is None:
            enabled = [a for a, default in cls.tag_assets.items() if default]
        else:
            enabled = [a for a in cls.tag_assets if a.value in enabled_tags]
        return list(cls.core_assets) + enabled

    @abstractmethod
    def compose(self, reel: Reel, **kwargs) -> FFmpegCommand:
        pass

    @abstractmethod
    def _get_block_segment(self, block: Block) -> Optional[dict]:
        """
        Returns a dictionary with keys: 'type', 'video', 'audio', 'duration'
        or None if the block produces no video segment.
        """
        pass

    def collect_segments_and_timings(self, reel: Reel):
        """
        Iterates through the reel to build the timeline of segments,
        synchronize subtitles, and extract media timings.
        """
        segments = []
        final_transcriptions = []
        current_time = 0.0

        logger.debug(
            "collect_segments_and_timings starting for reel with %d blocks",
            len(reel.blocks),
        )

        for b_idx, block in enumerate(reel.blocks):
            seg_info = self._get_block_segment(block)

            if seg_info:
                segments.append(seg_info)
                duration = seg_info.get("duration", 0.0)
                logger.debug(
                    "  Block %d (%s): Added to video (%.2fs)",
                    b_idx,
                    block.type,
                    duration,
                )
            else:
                duration = 0.0
                block_text = getattr(block, "text", "N/A")[:50]
                logger.debug(
                    "  Block %d (%s): Skipped (no video asset) - '%s...'",
                    b_idx,
                    block.type,
                    block_text,
                )

            # Handle Subtitles
            has_subs = False
            if block.assets:
                if block.assets.subtitles:
                    has_subs = True
                    trans = block.assets.subtitles
                    # Handle both TranscriptionVerbose object and dict (from JSON/Pickle)
                    words = getattr(trans, "words", None)
                    if words is None and isinstance(trans, dict):
                        words = trans.get("words", [])

                    if words:
                        shifted_words = [
                            TranscriptionWord(
                                word=w.word if hasattr(w, "word") else w["word"],
                                start=(w.start if hasattr(w, "start") else w["start"])
                                + current_time,
                                end=(w.end if hasattr(w, "end") else w["end"])
                                + current_time,
                            )
                            for w in words
                        ]

                        # Force a block boundary: append '.' to the last word if it doesn't
                        # already end with a break character. '.' is in break_characters so
                        # group_words_by_chars will split here, and in remove_chars so it's
                        # invisible in the displayed subtitle.
                        _break_chars = ".!?;:"
                        last_w = shifted_words[-1]
                        if not any(last_w.word.rstrip().endswith(c) for c in _break_chars):
                            shifted_words[-1] = TranscriptionWord(
                                word=last_w.word + ".",
                                start=last_w.start,
                                end=last_w.end,
                            )

                        final_transcriptions.append(
                            TranscriptionVerbose(
                                duration=(
                                    getattr(trans, "duration", 0.0)
                                    if hasattr(trans, "duration")
                                    else trans.get("duration", 0.0)
                                ),
                                language=(
                                    getattr(trans, "language", "en")
                                    if hasattr(trans, "language")
                                    else trans.get("language", "en")
                                ),
                                text=(
                                    getattr(trans, "text", "")
                                    if hasattr(trans, "text")
                                    else trans.get("text", "")
                                ),
                                words=shifted_words,
                            )
                        )
                        logger.debug(
                            "Block %d (%s): Subtitles found (%d words).",
                            b_idx,
                            block.type,
                            len(words),
                        )
                    else:
                        logger.debug(
                            "Block %d (%s): Subtitles present but no words found.",
                            b_idx,
                            block.type,
                        )
                else:
                    logger.debug(
                        "Block %d (%s): block.assets.subtitles is empty.",
                        b_idx,
                        block.type,
                    )
            else:
                logger.debug("Block %d (%s): block.assets is None.", b_idx, block.type)

            # IMPORTANT: Always increment current_time by the segment duration
            current_time += duration

        logger.debug("Total transcriptions collected: %d", len(final_transcriptions))
        final_subtitles = self.merge_transcriptions(final_transcriptions)

        # Pass final_transcriptions (the list of shifted absolute transcriptions per block)
        # to extract_media_timings.
        media_timings = self.extract_media_timings(reel.blocks, final_transcriptions)

        return segments, final_subtitles, media_timings, current_time

    def transcription_to_ass(
        self, transcription: TranscriptionVerbose, style: SubtitleStyle
    ) -> AssSubtitles:
        """
        Build an ASS subtitle file with optional karaoke effect.
        Groups words based on max_chars_per_line and respects break_characters.
        Only the currently spoken word is highlighted (if karaoke is enabled).
        """

        def fmt(t):
            # Convert seconds → h:mm:ss.cs (centiseconds)
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            cs = int((t - int(t)) * 100)
            return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

        def group_words_by_chars(words, max_chars, break_chars):
            """
            Group words based on character limit and break characters.
            Returns list of word groups.
            """
            groups = []
            current_group = []
            current_length = 0

            for w in words:
                word_text = w.word
                word_len = len(word_text)

                # Check if adding this word would exceed the limit
                # Account for spaces between words
                space_needed = 1 if current_group else 0
                total_length = current_length + space_needed + word_len

                # Check if word ends with a break character
                has_break_char = any(
                    word_text.rstrip().endswith(char) for char in break_chars
                )

                # Start new group if:
                # 1. Adding word exceeds character limit (and current group is not empty)
                # 2. Previous word ended with break character
                if current_group and (
                    total_length > max_chars
                    or any(
                        current_group[-1].word.rstrip().endswith(char)
                        for char in break_chars
                    )
                ):
                    groups.append(current_group)
                    current_group = [w]
                    current_length = word_len
                else:
                    current_group.append(w)
                    current_length = total_length

                # If this word has break char, close the group after adding it
                if has_break_char:
                    groups.append(current_group)
                    current_group = []
                    current_length = 0

            # Add remaining words
            if current_group:
                groups.append(current_group)

            return groups

        # === ASS header ===
        header = f"""[Script Info]
        PlayResX: 1080
        PlayResY: 1920
        ScaledBorderAndShadow: yes
        
        [V4+ Styles]
        Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,    ScaleX,    ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
        Style: Default,{style.font},{style.font_size},{style.color},{style.secondary_color},{style.stroke_color},{style.shadow_color},{style.       boldness},0,0,0,100,100,{style.letter_spacing},0,1,{style.stroke_width},{style.shadow_offset},{style.alignment},0,0,{style.offset_y},0
        
        [Events]
        Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        """

        events = [header]
        words = transcription.words

        # Group words based on character limit and break characters
        word_groups = group_words_by_chars(
            words, style.max_chars_per_line, style.break_characters
        )

        if style.karaoke_enabled:
            # Karaoke mode: highlight current word only
            for word_group in word_groups:
                # For each word in the group, create dialogue lines where only that word is highlighted
                for active_idx, active_word in enumerate(word_group):
                    start = fmt(active_word.start)
                    end = fmt(active_word.end)

                    # Build text with manual color overrides
                    text_parts = []
                    for idx, w in enumerate(word_group):
                        if idx == active_idx:
                            # This word is active - use secondary color (highlighted)
                            text_parts.append(
                                f"{{\\c{style.secondary_color}}}{w.word}{{\\c}}"
                            )
                        else:
                            # This word is not active - use primary color (default)
                            text_parts.append(f"{{\\c{style.color}}}{w.word}{{\\c}}")

                    text = " ".join(text_parts).translate(
                        {ord(x): "" for x in style.remove_chars}
                    )
                    events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        else:
            # Normal mode: all words same color, grouped display
            for word_group in word_groups:
                # Start time is the first word's start, end time is the last word's end
                start = fmt(word_group[0].start)
                end = fmt(word_group[-1].end)

                # Simple text without color changes
                text = " ".join([w.word for w in word_group]).translate(
                    {ord(x): "" for x in style.remove_chars}
                )
                events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return AssSubtitles("\n".join(events))

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe"""
        if not os.path.exists(video_path):
            raise FileNotFoundError(
                f"File not found for duration check: '{video_path}'. "
                "If you are resuming on a new environment (like Railway), "
                "ensure that the 'output/' directory from previous stages is available "
                "or that you haven't excluded it from your deployment."
            )

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"ffprobe failed for {video_path}: {error_msg}") from e

    def merge_transcriptions(
        self, subtitles: List[TranscriptionVerbose]
    ) -> TranscriptionVerbose:
        """
        Merge multiple TranscriptionVerbose objects into a single one.
        Assumes the per-block timings have already been shifted to absolute format.

        Args:
            subtitles: List of TranscriptionVerbose objects to merge

        Returns:
            Single merged TranscriptionVerbose object
        """
        if not subtitles:
            return TranscriptionVerbose(
                duration=0.0, language="english", text="", words=[]
            )

        # Merge all texts with spaces
        merged_text = " ".join(t.text for t in subtitles)

        # Merge all words
        merged_words = []
        for transcription in subtitles:
            merged_words.extend(transcription.words)

        # Calculate total duration
        total_duration = sum(t.duration for t in subtitles)

        # Use language from first transcription
        language = subtitles[0].language

        return TranscriptionVerbose(
            duration=total_duration,
            language=language,
            text=merged_text,
            segments=None,
            usage=None,
            words=merged_words,
        )

    def extract_media_timings(
        self,
        blocks: List[Block],
        absolute_subtitles: List[TranscriptionVerbose],
    ) -> List[MediaTiming]:
        """
        Extract absolute timing information for all media elements (images and latex)
        based on their word index triggers in each dialogue block.

        Args:
            blocks: List of Block objects containing dialogue and media triggers
            absolute_subtitles: Subtitles with absolute timings across entire video

        Returns:
            List of MediaTiming objects with absolute start/end times
        """
        media_timings = []
        dialogue_idx = 0

        logger.debug(
            "extract_media_timings starting. Blocks: %d, Subtitles: %d",
            len(blocks),
            len(absolute_subtitles),
        )

        for b_idx, block in enumerate(blocks):
            has_subtitles = bool(block.assets and block.assets.subtitles)

            # Dialogue items in absolute_subtitles only exist for blocks that HAD subtitles
            if has_subtitles:
                if dialogue_idx >= len(absolute_subtitles):
                    logger.warning("dialogue_idx %d out of range", dialogue_idx)
                    break

                absolute_trans = absolute_subtitles[dialogue_idx]
                dialogue_idx += 1

                media_list = getattr(block, "media", [])
                if not media_list:
                    continue

                logger.debug(
                    "  Block %d (%s) has %d media items. IDs in media_map: %s",
                    b_idx,
                    block.type,
                    len(media_list),
                    list(block.assets.media_map.keys()),
                )

                for m_idx, media_item in enumerate(media_list):
                    # Try to get from media_map or media_url_map
                    filepath = block.assets.media_map.get(media_item.id)
                    url = block.assets.media_url_map.get(media_item.id)

                    if not (filepath or url):
                        logger.debug(
                            "    Media %d (%s) skipped: ID %s not found in maps.",
                            m_idx,
                            media_item.type,
                            media_item.id,
                        )
                        continue

                    # Determine timing
                    trigger = media_item.trigger
                    if trigger:
                        start_word_idx = trigger.start_word_index
                        end_word_idx = trigger.end_word_index

                        if start_word_idx >= len(
                            absolute_trans.words
                        ) or end_word_idx >= len(absolute_trans.words):
                            logger.debug(
                                "    Media %d trigger [%d, %d] out of range (%d words). Falling back to full block.",
                                m_idx,
                                start_word_idx,
                                end_word_idx,
                                len(absolute_trans.words),
                            )
                            start_time = absolute_trans.words[0].start
                            end_time = absolute_trans.words[-1].end
                        else:
                            start_time = absolute_trans.words[start_word_idx].start
                            end_time = absolute_trans.words[end_word_idx].end
                    else:
                        logger.debug(
                            "    Media %d (%s) has NO TRIGGER. Defaulting to full block timing.",
                            m_idx,
                            media_item.type,
                        )
                        # Fallback: display for the whole block
                        if absolute_trans.words:
                            start_time = absolute_trans.words[0].start
                            end_time = absolute_trans.words[-1].end
                        else:
                            # If no words at all (shouldn't happen if has_subtitles is true), skip
                            logger.debug(
                                "    Media %d skipped: No words in transcription to calculate fallback.",
                                m_idx,
                            )
                            continue

                    timing = MediaTiming(
                        filepath=filepath or "",
                        start_time=start_time,
                        end_time=end_time,
                        media_type=media_item.type,
                        url=url,
                    )
                    media_timings.append(timing)
                    logger.debug(
                        "    Media %d (%s) EXTRACTED: %.2fs - %.2fs",
                        m_idx,
                        timing.media_type,
                        timing.start_time,
                        timing.end_time,
                    )
            else:
                # If block has media but no subtitles, we should log it
                media_list = getattr(block, "media", [])
                if media_list:
                    logger.debug(
                        "Block %d (%s) has %d media items but NO SUBTITLES. Skipping media extraction.",
                        b_idx,
                        block.type,
                        len(media_list),
                    )

        logger.debug("Total media timings extracted: %d", len(media_timings))
        return media_timings

    # --- Shared filter-graph building blocks used by the concrete templates ---

    def _segment_audio(self, graph: "FilterGraph", seg: dict, i: int) -> "FilterNode":
        """Silence-padded audio for a non-lipsync segment, mixed with voice if present.

        Generates silence for the exact segment duration so the timeline stays in
        sync, then mixes the voiceover on top (amix with normalize=0 to preserve
        the voice level).
        """
        silence = graph.add_raw(
            [],
            f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={seg['duration']}",
            f"silence_{i}",
        )
        if seg.get("audio"):
            _, a_in = graph.add_input(seg["audio"], f"seg_{i}_a")
            a_in = a_in.filter("aformat", channel_layouts="stereo")
            return graph.add_raw(
                [silence, a_in],
                "amix=inputs=2:duration=first:dropout_transition=0:normalize=0",
                f"seg_{i}_mix",
            )
        return silence

    def _concat_av(
        self, graph: "FilterGraph", v_nodes: list, a_nodes: list
    ) -> tuple["FilterNode", "FilterNode"]:
        """Concatenate per-segment video/audio nodes and loudness-normalize audio."""
        concat_v = graph.add_raw(
            v_nodes, f"concat=n={len(v_nodes)}:v=1:a=0", "lip_concat_v"
        )
        concat_a = graph.add_raw(
            a_nodes, f"concat=n={len(a_nodes)}:v=0:a=1", "lip_concat_a"
        )
        concat_a = concat_a.filter("loudnorm", I="-16", TP="-1.5", LRA="11")
        return concat_v, concat_a

    def _build_background(
        self, graph: "FilterGraph", current_time: float, apply_fps: bool = True
    ) -> "FilterNode":
        """Scale/crop the background video to 1080x1920 trimmed to the timeline."""
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        if apply_fps:
            bg_v = bg_v.filter("fps", fps=30)
        bg_v = bg_v.filter("trim", end=current_time).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")
        return bg_v

    def _overlay_media(
        self, graph: "FilterGraph", main_v: "FilterNode", media_timings: list
    ) -> "FilterNode":
        """Overlay every media item (image/latex/manim) with fade + horizontal slide."""
        for i, media in enumerate(media_timings):
            input_path = media.filepath
            if not os.path.isfile(media.filepath):
                if media.url:
                    input_path = resolve_media_url(media.url)
                else:
                    logger.warning(
                        "Skipping media %d (%s): file not found and no URL provided.",
                        i,
                        media.media_type,
                    )
                    continue

            media_v, _ = graph.add_input(input_path, f"media_{i}")
            display_end_time = media.end_time

            if media.media_type == "manim":
                # Manim is a video: scale to width, shift to its start time.
                manim_duration = (
                    self.get_video_duration(media.filepath)
                    if os.path.isfile(media.filepath)
                    else (media.end_time - media.start_time)
                )
                display_end_time = media.start_time + manim_duration

                media_v = (
                    media_v.filter("format", "yuva420p")
                    .filter("fps", fps=30)
                    .filter("scale", f"{self.manim_width}:-1")
                )
                if self.manim_style and self.manim_style.corner_radius > 0:
                    media_v = Animator.rounded_corners(
                        media_v, self.manim_style.corner_radius
                    )
                media_v = media_v.filter("setpts", f"PTS-STARTPTS+{media.start_time}/TB")
                is_static = False
            else:
                # Images/Latex are static.
                is_static = True

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                is_static=is_static,
                easing=self.media_fade_easing,
            )
            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
            )
            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{display_end_time})':eof_action=pass",
            )
        return main_v

    def _mix_music(
        self, graph: "FilterGraph", final_audio: "FilterNode", current_time: float
    ) -> "FilterNode":
        """Mix the template's background music (at 0.2 volume) under the audio, if any."""
        if not getattr(self, "music", None):
            return final_audio
        _, music_a = graph.add_input(self.music, "music")
        music_a = (
            music_a.filter("atrim", end=current_time)
            .filter("asetpts", "PTS-STARTPTS")
            .filter("volume", "0.2")
        )
        return graph.add_raw(
            [final_audio, music_a], "amix=inputs=2:normalize=0", "audio_mix"
        )


class FilterNode:
    """Represents a stream in the filter graph (e.g. [tmp_1])"""

    def __init__(self, graph: "FilterGraph", label: str):
        self.graph = graph
        self.label = label

    def filter(self, name: str, *args, **kwargs) -> "FilterNode":
        """Chain a filter to this node"""
        return self.graph.add_filter([self], name, *args, **kwargs)

    def __repr__(self):
        return f"[{self.label}]"


class FilterGraph:
    """Helper to build FFmpeg filter graphs without manual index management"""

    def __init__(self):
        self.inputs: List[Union[Path, str, dict]] = []
        self.input_labels: List[str] = []
        self.chains: List[str] = []
        self._counter = 0

    def add_input(
        self, path: Union[str, Path, dict], label: str = None
    ) -> tuple[FilterNode, FilterNode]:
        """Adds an input and returns (video_node, audio_node)"""
        idx = len(self.inputs)
        # Store dicts as-is, convert strings/paths to Path objects
        if isinstance(path, dict):
            self.inputs.append(path)
        else:
            self.inputs.append(Path(path))

        self.input_labels.append(label or f"input_{idx}")
        return FilterNode(self, f"{idx}:v"), FilterNode(self, f"{idx}:a")

    def add_filter(
        self, inputs: List[FilterNode], name: str, *args, **kwargs
    ) -> FilterNode:
        """Adds a filter command"""
        # Format arguments: filter=arg1:arg2:key=value
        arg_list = [str(a) for a in args]
        arg_list.extend(f"{k}={v}" for k, v in kwargs.items())
        params = ":".join(arg_list)
        filter_str = f"{name}={params}" if params else name

        return self.add_raw(inputs, filter_str)

    def add_raw(
        self, inputs: List[FilterNode], filter_str: str, output_label: str = None
    ) -> FilterNode:
        """Adds a raw filter string for complex cases (like overlay expressions)"""
        if not output_label:
            output_label = f"tmp_{self._counter}"
            self._counter += 1

        input_str = "".join(str(n) for n in inputs)
        self.chains.append(f"{input_str} {filter_str} [{output_label}]")
        return FilterNode(self, output_label)

    def build(
        self, video_out: FilterNode, audio_out: FilterNode, extra_args: List[str]
    ) -> FFmpegCommand:
        args = ["-filter_complex", ";".join(self.chains)]
        args.extend(["-map", str(video_out), "-map", str(audio_out)])
        args.extend(extra_args)
        return FFmpegCommand(
            inputs=self.inputs, args=args, input_labels=self.input_labels
        )


class Animator:
    """Helper for generating FFmpeg animation expressions and filters"""

    @staticmethod
    def _get_easing(p: str, type: str = "linear") -> str:
        """Returns FFmpeg expression for easing function applied to normalized time p (0-1)"""
        if type == "linear":
            return p

        # Quadratic
        if type == "ease_in_quad":
            return f"pow({p},2)"
        if type == "ease_out_quad":
            return f"(1-pow(1-{p},2))"
        if type == "ease_in_out_quad":
            return f"if(lt({p},0.5), 2*pow({p},2), 1-pow(-2*{p}+2,2)/2)"

        # Cubic
        if type == "ease_in_cubic":
            return f"pow({p},3)"
        if type == "ease_out_cubic":
            return f"(1-pow(1-{p},3))"
        if type == "ease_in_out_cubic":
            return f"if(lt({p},0.5), 4*pow({p},3), 1-pow(-2*{p}+2,3)/2)"

        # Quartic
        if type == "ease_in_quart":
            return f"pow({p},4)"
        if type == "ease_out_quart":
            return f"(1-pow(1-{p},4))"
        if type == "ease_in_out_quart":
            return f"if(lt({p},0.5), 8*pow({p},4), 1-pow(-2*{p}+2,4)/2)"

        return p

    @staticmethod
    def rounded_corners(node: FilterNode, radius: int) -> FilterNode:
        if radius <= 0:
            return node

        # Ensure alpha format
        node = node.filter("format", "yuva420p")
        node = node.filter("colorchannelmixer", aa=1.0)

        # GEQ filter for rounded corners
        # Formula: alpha = 0 if outside rounded corner, 255 inside.
        expr = (
            f"if(gt(abs(W/2-X),W/2-{radius})*gt(abs(H/2-Y),H/2-{radius}),"
            f"if(lte(hypot({radius}-(W/2-abs(W/2-X)),{radius}-(H/2-abs(H/2-Y))),{radius}),255,0),255)"
        )

        # Use quotes for expressions to handle commas safely and preserve all channels
        return node.filter(
            "geq", lum="'p(X,Y)'", cb="'p(X,Y)'", cr="'p(X,Y)'", a=f"'{expr}'"
        )

    @staticmethod
    def slide_horizontal(
        start_time: float,
        end_time: float,
        duration: float = 0.4,
        enter_from: str = "left",  # "left", "right", "none"
        exit_to: str = "right",  # "left", "right", "none"
        easing: str = "ease_in_out_quart",
        width_var: str = "w",
        parent_width_var: str = "W",
    ) -> str:
        center = f"(({parent_width_var}-{width_var})/2)"

        # Normalized time 0->1
        t_entry = f"min(max((t-{start_time})/{duration},0),1)"
        p_entry = Animator._get_easing(t_entry, easing)

        # Entry Logic
        if enter_from == "left":
            # Linear interp from -w to center
            entry = f"-{width_var} + ({center} + {width_var}) * {p_entry}"
        elif enter_from == "right":
            entry = f"{parent_width_var} - ({parent_width_var} - {center}) * {p_entry}"
        else:
            entry = center

        # Exit Logic
        # Exit starts at end_time - duration
        exit_start = f"({end_time}-{duration})"
        t_exit = f"min(max((t-{exit_start})/{duration},0),1)"
        p_exit = Animator._get_easing(t_exit, easing)

        if exit_to == "right":
            # Linear interp from center to W
            exit_expr = f"{center} + ({parent_width_var} - {center}) * {p_exit}"
        elif exit_to == "left":
            exit_expr = f"{center} - ({center} + {width_var}) * {p_exit}"
        else:
            exit_expr = center

        # Composite Expression
        return (
            f"if(lt(t, {start_time}+{duration}), {entry}, "
            f"if(gt(t, {end_time}-{duration}), {exit_expr}, {center}))"
        )

    @staticmethod
    def fade(
        node: FilterNode,
        start_time: float,
        end_time: float,
        duration: float = 0.4,
        is_static: bool = True,
        easing: str = "linear",
    ) -> FilterNode:
        """Applies fade-in and fade-out to the alpha channel"""
        if is_static:
            node = node.filter("loop", loop=-1, size=1, start=0)
            node = node.filter("trim", duration=end_time + 1.0)
            node = node.filter("setpts", "N/FRAME_RATE/TB")
            node = node.filter("format", "yuva420p")

        if easing == "linear":
            return node.filter(
                "fade", t="in", st=start_time, d=duration, alpha=1
            ).filter("fade", t="out", st=end_time - duration, d=duration, alpha=1)

        # Custom easing using geq
        t_in = f"min(max((t-{start_time})/{duration},0),1)"
        p_in = Animator._get_easing(t_in, easing)

        exit_start = f"({end_time}-{duration})"
        t_out = f"min(max((t-{exit_start})/{duration},0),1)"
        p_out = Animator._get_easing(t_out, easing)

        # For fade out, alpha should go from 1 to 0. p_out goes from 0 to 1.
        expr = f"if(lt(t, {start_time}+{duration}), {p_in}, if(gt(t, {end_time}-{duration}), 1-{p_out}, 1))"

        full_expr = f"alpha(X,Y)*({expr})"
        return node.filter(
            "geq", lum="'p(X,Y)'", cb="'p(X,Y)'", cr="'p(X,Y)'", a=f"'{full_expr}'"
        )
