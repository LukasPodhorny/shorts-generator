from dataclasses import dataclass
import os
from openai.types.audio import TranscriptionVerbose
import subprocess
import tempfile
from pydantic import BaseModel
from aishorts.modules.lipsync.lipsync_providers import LipsyncResult
from aishorts.modules.tts.tts_providers import TTSResult
from aishorts.modules.script.script import Reel, Block
import uuid
from aishorts.modules.provider import Provider
from abc import abstractmethod
from enum import Enum
from typing import List
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from openai.types.audio import TranscriptionVerbose, TranscriptionWord
from aishorts.modules.image.image_providers import ImageResult
from aishorts.modules.latex.latex_providers import LatexResult


class AssetType(Enum):
    SCRIPT = "script"
    VOICE = "voice"
    LIPSYNC = "lipsync"
    SUBTITLES = "subtitles"
    IMAGES = "images"
    LATEX = "latex"


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

        return cmd


@dataclass
class TemplateAssets:
    reel_script: Reel | None = None
    lipsync_videos: list[LipsyncResult] | None = None
    subtitles: TranscriptionVerbose | None = None
    voiceovers: list[TTSResult] | None = None
    images: list[ImageResult] | None = None
    latex: list[LatexResult] | None = None


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
    subtitle_style: SubtitleStyle | None = None


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
    def compose(self, template_assets: TemplateAssets, **kwargs) -> FFmpegCommand:
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

    @staticmethod
    def nvenc_available() -> bool:
        """
        Check if h264_nvenc actually works (not only exists in the encoder list).
        This tries encoding a single black frame with NVENC.
        """

        test_out = tempfile.NamedTemporaryFile(suffix=".mp4").name

        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=16x16:d=0.1",
            "-c:v",
            "h264_nvenc",
            "-y",
            test_out,
        ]

        try:
            subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
            )
            return True
        except:
            return False

    video_codec = "h264_nvenc" if nvenc_available() else "libx264"

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
        images: list[ImageResult],  # List of ImageResult
        latex: list[LatexResult],  # List of LatexResult
    ) -> List[MediaTiming]:
        """
        Extract absolute timing information for all media elements (images and latex)
        based on their word index triggers in each dialogue block.

        Args:
            blocks: List of Block objects containing dialogue and media triggers
            absolute_subtitles: Subtitles with absolute timings across entire video
            images: List of ImageResult objects
            latex: List of LatexResult objects

        Returns:
            List of MediaTiming objects with absolute start/end times
        """
        media_timings = []
        image_idx = 0
        latex_idx = 0
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
                if media_type == "image" and image_idx < len(images):
                    filepath = images[image_idx].media.path
                    image_idx += 1
                elif media_type == "latex" and latex_idx < len(latex):
                    filepath = latex[latex_idx].media.path
                    latex_idx += 1

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
