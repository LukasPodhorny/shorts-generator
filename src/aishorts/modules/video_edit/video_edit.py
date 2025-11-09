from dataclasses import dataclass
from aishorts.utils.registry import register_edit_template
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    CompositeAudioClip,
)
from moviepy.video.tools.subtitles import SubtitlesClip
import os
from aishorts.utils.r2_handler import CloudflareR2
from openai.types.audio import TranscriptionVerbose
from aishorts.tests.sub_test import TEST_SUBTITLES, TEST_SUBTITLES_FORCED_ALIGNMENT
from aishorts.modules.video_edit.asset_type import AssetType


@dataclass
class TemplateAssets:
    lipsync_video: str | None = None
    # IT WILL BE .SRT MOST PROBABLY!!
    subtitles: TranscriptionVerbose | None = None
    voiceover: str | None = None


@dataclass
class SubtitleStyle:
    provider: str = "elevenlabs"
    font: str | None = None
    font_size: int = 150
    color: str = "white"
    stroke_width: int = 10
    stroke_color: str = "black"
    size: tuple[int, int] = (1080, 500)
    offset_x: int = 0
    offset_y: int = -60

    def textclip_kwargs(self) -> dict:
        return {
            "font": self.font,
            "font_size": self.font_size,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "stroke_color": self.stroke_color,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, data: dict):
        # Convert size from list to tuple if loaded from JSON
        if "size" in data and isinstance(data["size"], list):
            data["size"] = tuple(data["size"])
        return cls(**data)


@dataclass
class TemplateConfig:
    bg_video: str | None = None
    music: str | None = None
    subtitle_style: SubtitleStyle | None = None
    # add more like stroke width etc...

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

    def generate_subtitles(
        self,
        subtitles: TranscriptionVerbose,
        subtitle_style: SubtitleStyle,
        screen_width=1080,
        screen_height=1920,
    ) -> SubtitlesClip:

        subtitle_words = subtitles.words
        size = subtitle_style.size
        offset_x = subtitle_style.offset_x
        offset_y = subtitle_style.offset_y

        # workaround for keeping the y position same:
        # tall character (|), so the text height stays always the same
        # white spaces -> so it overflows and is not seen
        padding = " " * 60
        generator = lambda txt: TextClip(
            text=f"|{padding}{txt}{padding}|", **subtitle_style.textclip_kwargs()
        )

        subs = []
        for w in subtitle_words:
            subs.append(((w.start, w.end), w.word))

        subtitles_clip = SubtitlesClip(
            subtitles=subs, make_textclip=generator
        ).with_position(
            (
                screen_width / 2 - size[0] / 2 + offset_x,
                screen_height / 2 - size[1] / 2 + offset_y,
            )
        )

        return subtitles_clip


@register_edit_template("gameplay")
class GameplayTemplate(EditTemplate):
    # later maybe image timeline or something...
    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
    ]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style

    def compose(self, template_assets: TemplateAssets):

        # === Load media ===
        lipsync = VideoFileClip(template_assets.lipsync_video).resized(width=1080)
        gameplay = VideoFileClip(self.bg_video).with_duration(lipsync.duration)
        music = AudioFileClip(self.music).with_duration(lipsync.duration)

        # === Crop to vertical format (if needed) ===
        gameplay = gameplay.cropped(
            x_center=gameplay.w / 2, y_center=lipsync.h / 2, width=1080, height=960
        )
        lipsync = lipsync.cropped(
            x_center=lipsync.w / 2, y_center=lipsync.h / 2, width=1080, height=960
        )

        # === Position clips ===
        lipsync = lipsync.with_position(("center", 0))
        gameplay = gameplay.with_position(("center", 960))

        # === Add subtitles ===
        subtitles = self.generate_subtitles(
            subtitles=template_assets.subtitles,
            subtitle_style=self.subtitle_style,
        )

        # === Compose ===
        final = CompositeVideoClip(
            [
                lipsync,
                gameplay,
                subtitles,
            ],
            size=(1080, 1920),
        )
        mixed_audio = CompositeAudioClip(
            [lipsync.audio.with_volume_scaled(5), music.with_volume_scaled(0.2)]
        )
        final = final.with_audio(mixed_audio)

        # === Export ===
        output_path = CloudflareR2.get_random_filepath(EditTemplate.OUTPUT_DIR, ".mp4")
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
    assets = TemplateAssets(
        lipsync_video="/home/lukaspodhorny/projects/shorts-generator/output/lipsync/609dbff94b4249e5bcb5b69150dfc981.mp4",
        subtitles=TEST_SUBTITLES_FORCED_ALIGNMENT,
    )
    config = TemplateConfig(
        bg_video="assets/bg_video/gameplay.mp4",
        music="assets/music/music.mp3",
        subtitle_style=SubtitleStyle(font="assets/fonts/NotoSans-Bold.ttf"),
    )
    template = GameplayTemplate(config)
    template.compose(assets)
