import asyncio
from script_generator import ScriptGenerator
from voice_generator import VoiceGenerator
from lipsync_generator import LipsyncGenerator
from dataclasses import dataclass, field
from subtitle_generator import SubtitleGenerator
from video_edit import VideoTemplate
from video_generator import VideoGenerator
from avatar import Avatar
from registry import EDIT_TEMPLATES
from asset_type import AssetType
from video_edit import TemplateAssets
from templates_config import TEMPLATES
from avatars_config import AVATARS


@dataclass
class ScriptConfig:
    model: str = "gpt-5"
    builtin_reader: bool = True
    max_output_tokens: int = 1800


@dataclass
class SubtitleConfig:
    provider: str = "elevenlabs"
    provider_config: dict = field(default_factory=dict)


@dataclass
class ShortsConfig:
    avatar: Avatar
    video_template: VideoTemplate
    script_config: ScriptConfig = field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = field(default_factory=SubtitleConfig)


class ShortsGenerator:
    def __init__(self, avatar: Avatar, shorts_config: ShortsConfig):
        self.script_gen = ScriptGenerator(
            avatar=avatar, **shorts_config.script_config.__dict__
        )
        self.voice_gen = VoiceGenerator(voice=avatar.voice, return_url=True)
        self.lipsync_gen = LipsyncGenerator(avatar=avatar)
        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config,
        )
        self.video_gen = VideoGenerator(video_template=shorts_config.video_template)

        self.video_template = shorts_config.video_template

    async def generate_short(
        self,
        video_template: VideoTemplate,
        files: list[str] | None = None,
        user_input: str | None = None,
    ):
        required_assets = EDIT_TEMPLATES.get(
            self.video_template.edit_template.lower()
        ).required_assets

        template_assets = TemplateAssets()

        print("Generating script...")
        if AssetType.SCRIPT in required_assets:
            script = self.script_gen.generate_script(files=files, user_input=user_input)

        print("Generating voiceover...")
        if AssetType.VOICE in required_assets:
            template_assets.voiceover, result_url = await self.voice_gen.generate_voice(
                script
            )
        template_assets.voiceover = "output/tts/274d8df3035b4180a1e6840b1a4e697d.wav"
        result_url = "https://files.catbox.moe/0ascjc.wav"

        print("Generating lipsync video and subtitles...")
        tasks = []
        if AssetType.LIPSYNC in required_assets:
            tasks.append(self.lipsync_gen.generate_lipsync(result_url))

        if AssetType.SUBTITLES in required_assets:
            tasks.append(
                self.subtitle_gen.generate_subtitles(
                    audio_file=template_assets.voiceover, transcription_text=script
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results back
        idx = 0
        if AssetType.LIPSYNC in required_assets:
            template_assets.lipsync_video = results[idx]
            idx += 1
        if AssetType.SUBTITLES in required_assets:
            template_assets.subtitles = results[idx]

        print("Generating final video...")
        video_generator = VideoGenerator(video_template=video_template)
        return video_generator.compose(template_assets=template_assets)


async def main():
    avatar = AVATARS["biden"]
    video_template = TEMPLATES["gameplay_0"]
    config = ShortsConfig(avatar=avatar, video_template=video_template)

    generator = ShortsGenerator(avatar, config)

    output_path = await generator.generate_short(
        video_template=video_template,
        user_input="Why cats are better than dogs.",
    )

    print(output_path)


if __name__ == "__main__":
    asyncio.run(main())
