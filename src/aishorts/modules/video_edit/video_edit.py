from dataclasses import dataclass
import os
from openai.types.audio import TranscriptionVerbose
import subprocess
from pydantic import BaseModel, Field
from aishorts.modules.lipsync.lipsync_providers import LipsyncResult
from aishorts.modules.tts.tts_providers import TTSResult
from aishorts.modules.script.script import Reel, Block, AssetType
import uuid
from aishorts.modules.provider import Provider
from abc import abstractmethod
from enum import Enum
from typing import List
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from aishorts.utils.image_utils import ImageStyle


@dataclass
class MediaTiming:
    """Represents the absolute timing for a media element (image or latex)"""

    filepath: str
    start_time: float
    end_time: float
    media_type: str


@dataclass
class FFmpegCommand:
    """
    FFmpeg command with ordered inputs.
    The command references inputs by their index [0], [1], [2], etc.
    """

    # The actual inputs in order - these get replaced by provider
    inputs: List[Path]

    # The filter graph and other args (already have correct indices)
    args: List[str]

    # Video codec for optimatization
    video_codec: str = None

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
            cmd.extend(["-i", input_path])

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
    bg_video: str | None = None
    music: str | None = None
    subtitle_style: SubtitleStyle | None = Field(default_factory=SubtitleStyle)
    chromakey_color: str | None = "0x00FF00"
    chromakey_similarity: float | None = 0.17
    chromakey_blend: float | None = 0.2
    image_style: ImageStyle | None = Field(default_factory=ImageStyle)
    max_image_width: int | None = 800
    max_image_height: int | None = 600
    latex_style: ImageStyle | None = Field(default_factory=ImageStyle)
    latex_width: int | None = 600
    latex_height: int | None = 300
    question_graphic: str = "MotionGraphicQuestion"

    def get_question_graphic_class(self):
        from aishorts.modules.motion_graphic.questions import MotionGraphicQuestion

        registry = {
            "MotionGraphicQuestion": MotionGraphicQuestion,
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

    @abstractmethod
    def compose(self, reel: Reel, **kwargs) -> FFmpegCommand:
        pass

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def convert_to_absolute_timing(
        self, subtitles: List[TranscriptionVerbose]
    ) -> List[TranscriptionVerbose]:
        """
        Convert relative word timings in each TranscriptionVerbose to absolute timings
        based on the video's total timeline.

        Args:
            subtitles: List of TranscriptionVerbose objects with relative timings

        Returns:
            List of TranscriptionVerbose objects with absolute timings
        """
        result = []
        cumulative_time = 0.0

        for transcription in subtitles:
            # Create a new TranscriptionVerbose with adjusted word timings
            adjusted_words = []

            for word in transcription.words:
                adjusted_word = TranscriptionWord(
                    end=word.end + cumulative_time,
                    start=word.start + cumulative_time,
                    word=word.word,
                )
                adjusted_words.append(adjusted_word)

            adjusted_transcription = TranscriptionVerbose(
                duration=transcription.duration,
                language=transcription.language,
                text=transcription.text,
                segments=transcription.segments,
                usage=transcription.usage,
                words=adjusted_words,
            )

            result.append(adjusted_transcription)
            cumulative_time += transcription.duration

        return result

    def merge_transcriptions(
        self, subtitles: List[TranscriptionVerbose]
    ) -> TranscriptionVerbose:
        """
        Merge multiple TranscriptionVerbose objects into a single one.
        Assumes timings are already in absolute format (use convert_to_absolute_timing first).

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
        blocks: list[Block],  # List of Block objects from your Reel
        absolute_subtitles: list[TranscriptionVerbose],
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

        for block in blocks:
            if block.type != "dialogue":
                continue

            # Get the corresponding transcription for this dialogue
            if dialogue_idx >= len(absolute_subtitles):
                break

            absolute_trans = absolute_subtitles[dialogue_idx]

            # Check if this block has media
            if block.media is not None:
                trigger = block.media.trigger
                media_type = block.media.type

                # Get start and end word indices
                start_word_idx = trigger.start_word_index
                end_word_idx = trigger.end_word_index

                # Validate indices
                if start_word_idx >= len(absolute_trans.words) or end_word_idx >= len(
                    absolute_trans.words
                ):
                    print(
                        f"Warning: Word indices out of range for dialogue {dialogue_idx}"
                    )
                    dialogue_idx += 1
                    continue

                # Get absolute timing from the words
                start_time = absolute_trans.words[start_word_idx].start
                end_time = absolute_trans.words[end_word_idx].end

                # Get the filepath based on media type
                filepath = None
                if (
                    media_type == "image"
                    and block.assets
                    and block.assets.image_filepath
                ):
                    filepath = block.assets.image_filepath
                elif (
                    media_type == "latex"
                    and block.assets
                    and block.assets.latex_filepath
                ):
                    filepath = block.assets.latex_filepath

                if filepath:
                    media_timings.append(
                        MediaTiming(
                            filepath=filepath,
                            start_time=start_time,
                            end_time=end_time,
                            media_type=media_type,
                        )
                    )

            dialogue_idx += 1

        return media_timings


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
        self.inputs: List[Path] = []
        self.input_labels: List[str] = []
        self.chains: List[str] = []
        self._counter = 0

    def add_input(
        self, path: str | Path, label: str = None
    ) -> tuple[FilterNode, FilterNode]:
        """Adds an input and returns (video_node, audio_node)"""
        idx = len(self.inputs)
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

        expr = f"if(lt(t, {start_time}+{duration}), {p_in}, if(gt(t, {end_time}-{duration}), 1-{p_out}, 1))"
        return node.filter("geq", a=f"alpha(X,Y)*({expr})")
