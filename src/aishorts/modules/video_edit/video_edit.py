from dataclasses import dataclass
import os
from openai.types.audio import TranscriptionVerbose
import subprocess
import tempfile
from pydantic import BaseModel


@dataclass
class TemplateAssets:
    lipsync_video: str | None = None
    subtitles: TranscriptionVerbose | None = None
    voiceover: str | None = None


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


class EditTemplate:
    OUTPUT_DIR = os.getenv("VIDEO_OUTPUT_DIR") or "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def compose(self):
        raise NotImplementedError("You must implement compose function.")

    def transcription_to_ass(
        self, transcription: TranscriptionVerbose, style: SubtitleStyle
    ) -> str:
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

        return "\n".join(events)

    def nvenc_available(self) -> bool:
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
