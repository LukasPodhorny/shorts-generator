import asyncio
from script_generator import ScriptGenerator
from voice_generator import VoiceGenerator
from lipsync_generator import LipsyncGenerator
from dataclasses import dataclass, field
from subtitle_generator import SubtitleGenerator
from video_edit import SubtitleStyle, VideoTemplate
from video_generator import VideoGenerator
from avatar import Avatar
from registry import EDIT_TEMPLATES


@dataclass
class ScriptConfig:
    script_model: str = "gpt-5"
    script_builtin_reader: bool = True
    script_max_output_tokens: int = 1800


@dataclass
class SubtitleConfig:
    provider: str = "elevenlabs"
    provider_config: dict = field(default_factory=dict)


@dataclass
class ShortsConfig:
    avatar: Avatar
    video_template: VideoTemplate
    script_config: ScriptConfig = ScriptConfig()
    subtitle_config: SubtitleConfig = SubtitleConfig()


class ShortsGenerator:
    def __init__(self, avatar: Avatar, shorts_config: ShortsConfig):
        self.script_gen = ScriptGenerator(
            avatar=avatar, **shorts_config.script_config.__dict__
        )
        self.voice_gen = VoiceGenerator(avatar=avatar.voice)
        self.lipsync_gen = LipsyncGenerator(avatar=avatar)
        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config
        )
        self.video_gen = VideoGenerator(video_template=shorts_config.video_template)

        self.video_template = shorts_config.video_template

    def generate_short(self):
        required_assets = EDIT_TEMPLATES.get(
            self.video_template.edit_template.lower()
        ).required_assets
