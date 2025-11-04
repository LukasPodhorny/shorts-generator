from dataclasses import dataclass
from registry import register_edit_template
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    CompositeAudioClip,
)
from moviepy.video.tools.subtitles import SubtitlesClip
import os
from r2_handler import CloudflareR2
from openai.types.audio import TranscriptionVerbose
from sub_test import TEST_SUBTITLES, TEST_SUBTITLES_FORCED_ALIGNMENT


@dataclass
class TemplateAssets:
    lipsync_video: str | None = None
    # IT WILL BE .SRT MOST PROBABLY!!
    subtitles: TranscriptionVerbose | None = None
    voiceover: str | None = None


@dataclass
class SubtitleConfig:
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


@dataclass
class TemplateConfig:
    bg_video: str | None = None
    music: str | None = None
    subtitle_style: SubtitleConfig | None = None
    # add more like stroke width etc...


@dataclass
class VideoTemplate:
    edit_template: str
    template_config: TemplateConfig


class EditTemplate:
    OUTPUT_DIR = os.getenv("VIDEO_OUTPUT_DIR") or "output/videos"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def compose(self):
        raise NotImplementedError("You must implement compose function.")

    def generate_subtitles(
        self,
        subtitles: TranscriptionVerbose,
        subtitle_config: SubtitleConfig,
        screen_width=1080,
        screen_height=1920,
    ) -> SubtitlesClip:

        subtitle_words = subtitles.words
        size = subtitle_config.size
        offset_x = subtitle_config.offset_x
        offset_y = subtitle_config.offset_y

        # workaround for keeping the y position same:
        # tall character (|), so the text height stays always the same
        # white spaces -> so it overflows and is not seen
        padding = " " * 30
        generator = lambda txt: TextClip(
            text=f"|{padding}{txt}{padding}|", **subtitle_config.textclip_kwargs()
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
    required_assets = ["voiceover", "lipsync_video", "subtitles"]

    def __init__(
        self, template_assets: TemplateAssets, template_config: TemplateConfig
    ):
        # self.voiceover = template_assets.voiceover
        self.lipsync_video = template_assets.lipsync_video
        self.subtitles = template_assets.subtitles

        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style

    def compose(self):

        # === Load media ===
        gameplay = VideoFileClip(self.bg_video).resized(width=1080)
        lipsync = VideoFileClip(self.lipsync_video).resized(width=1080)
        music = AudioFileClip(self.music)

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
            subtitles=self.subtitles,
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
        mixed_audio = CompositeAudioClip([lipsync.audio, music.with_volume_scaled(0.4)])
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
        lipsync_video="output/lipsync/b7ab285994464d9dbfc62d485427f2f1.mp4",
        subtitles=TEST_SUBTITLES_FORCED_ALIGNMENT,
    )
    config = TemplateConfig(
        bg_video="assets/bg_video/gameplay_20.mp4",
        music="assets/music/music_20.mp3",
        subtitle_style=SubtitleConfig(font="assets/fonts/NotoSans-Bold.ttf"),
    )
    template = GameplayTemplate(assets, config)
    template.compose()
