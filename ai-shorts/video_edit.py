from dataclasses import dataclass
from registry import register_edit_template
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
)


@dataclass
class TemplateAssets:
    voiceover: str
    lipsync_video: str | None = None
    # IT WILL BE .SRT MOST PROBABLY!!
    subtitles: str | None = None


@dataclass
class TemplateConfig:
    edit_template: str
    bg_video: str | None = None
    music: str | None = None


class EditTemplate:
    def compose(self):
        raise NotImplementedError("You must implement compose function.")


@register_edit_template("gameplay")
class GameplayTemplate(EditTemplate):
    required_assets = ["voiceover", "bg_video", "subtitles"]

    def __init__(
        self, template_assets: TemplateAssets, template_config: TemplateConfig
    ):
        self.template_assets = template_assets
        self.template_config = template_config

        self.voiceover = template_assets.voiceover
        self.lipsync_video = template_assets.lipsync_video
        self.subtitles = template_assets.subtitles


def compose_video(
    lipsync_path: str,
    gameplay_path: str,
    audio_path: str,
    subtitles: list[tuple[str, str, float, float]],  # [(text, color, start, end)]
    output_path="final_video.mp4",
):
    """
    subtitles format: [(text, color, start_time, end_time)]
    Example: [("HELLO THERE!", "yellow", 0.0, 2.5)]
    """

    # === Load media ===
    gameplay = VideoFileClip(gameplay_path).resized(width=1080)
    lipsync = VideoFileClip(lipsync_path).resized(width=1080)
    audio = AudioFileClip(audio_path)

    # === Crop to vertical format (if needed) ===
    gameplay = gameplay.cropped(x_center=gameplay.w / 2, width=1080, height=960)
    lipsync = lipsync.cropped(x_center=lipsync.w / 2, width=1080, height=960)

    # === Position clips ===
    lipsync = lipsync.with_position(("center", "top"))
    gameplay = gameplay.with_position(("center", "bottom"))

    # === Add subtitles ===
    subtitle_clips = []
    for text, color, start, end in subtitles:
        txt = (
            TextClip(
                text,
                fontsize=70,
                color=color,
                font="Impact",  # or path to .ttf
                stroke_color="black",
                stroke_width=4,
                size=(1080, None),
                method="caption",
            )
            .with_position(("center", "center"))
            .with_start(start)
            .with_end(end)
        )
        subtitle_clips.append(txt)

    # === Compose ===
    final = CompositeVideoClip([lipsync, gameplay, *subtitle_clips], size=(1080, 1920))
    final = final.with_audio(audio)

    # === Export ===
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="medium",
        threads=4,
    )


# Example usage
if __name__ == "__main__":
    subtitles = [
        ("WHAT IS PHOTOSYNTHESIS?", "yellow", 0, 2.2),
        ("IT'S HOW PLANTS EAT LIGHT BRO", "white", 2.2, 5.1),
    ]
    compose_video(
        lipsync_path="lipsync.mp4",
        gameplay_path="minecraft.mp4",
        audio_path="voice.mp3",
        subtitles=subtitles,
    )
