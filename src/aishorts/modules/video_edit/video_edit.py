from dataclasses import dataclass
import os
from openai.types.audio import TranscriptionVerbose
import subprocess
import tempfile


@dataclass
class TemplateAssets:
    lipsync_video: str | None = None
    subtitles: TranscriptionVerbose | None = None
    voiceover: str | None = None


@dataclass
class SubtitleStyle:
    font: str = "Arial"
    font_size: int = 250
    color: str = "&H00FFFFFF"
    stroke_width: int = 12
    stroke_color: str = "&H00000000"
    shadow_color: str = "&H64000000"
    boldness: int = 0
    letter_spacing: int = 0
    shadow_offset: int = 5
    alignment: int = 5
    offset_y: int = 100

    @classmethod
    def from_dict(cls, data: dict):
        if "size" in data and isinstance(data["size"], list):
            data["size"] = tuple(data["size"])
        return cls(**data)


@dataclass
class TemplateConfig:
    bg_video: str | None = None
    music: str | None = None
    subtitle_style: SubtitleStyle | None = None

    @classmethod
    def from_dict(cls, data: dict):
        subtitle_style = data.get("subtitle_style")
        if isinstance(subtitle_style, dict):
            data["subtitle_style"] = SubtitleStyle.from_dict(subtitle_style)
        return cls(**data)


@dataclass
class VideoTemplate:
    edit_template: str
    template_config: TemplateConfig

    @classmethod
    def from_dict(cls, data: dict):
        data["template_config"] = TemplateConfig.from_dict(data["template_config"])
        return cls(**data)


class EditTemplate:
    OUTPUT_DIR = os.getenv("VIDEO_OUTPUT_DIR") or "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def compose(self):
        raise NotImplementedError("You must implement compose function.")

    def transcription_to_ass(
        self, transcription: TranscriptionVerbose, style: SubtitleStyle
    ) -> str:
        """
        Build an ASS subtitle file with one event per WORD.
        The text appears in the CENTER with outline & shadow.
        """

        def fmt(t):
            # Convert seconds → h:mm:ss.cs (centiseconds)
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            cs = int((t - int(t)) * 100)
            return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

        # === ASS header ===
        header = f"""[Script Info]

        PlayResX: 1080
        PlayResY: 1920
        ScaledBorderAndShadow: yes

        [V4+ Styles]
        Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,    ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
        Style: Default,{style.font},{style.font_size},{style.color},&H00000000,{style.stroke_color},{style.shadow_color},{style.boldness},0,0,0,100,100,{style.letter_spacing},0,1,{style.stroke_width},{style.shadow_offset},{style.alignment},0,0,{style.offset_y},0

        [Events]
        Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        """

        events = [header]

        for w in transcription.words:
            start = fmt(w.start)
            end = fmt(w.end)
            text = w.word
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
