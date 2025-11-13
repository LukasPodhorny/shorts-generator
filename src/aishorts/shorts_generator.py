import asyncio
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from dataclasses import dataclass, field
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.video_edit.video_edit import VideoTemplate, TemplateAssets
from aishorts.modules.video_edit.video_generator import VideoGenerator
from aishorts.modules.avatar import Avatar
from aishorts.utils.registry import EDIT_TEMPLATES
from aishorts.modules.video_edit.asset_type import AssetType


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
    def __init__(
        self,
        shorts_config: ShortsConfig,
        tts_api_key: str | None,
        lipsync_api_key: str | None,
        subtitles_api_key: str | None,
    ):
        self.avatar = shorts_config.avatar
        self.script_gen = ScriptGenerator(
            avatar=self.avatar, **shorts_config.script_config.__dict__
        )
        self.voice_gen = VoiceGenerator(
            voice=self.avatar.voice, return_url=True, api_key=tts_api_key
        )
        self.lipsync_gen = LipsyncGenerator(avatar=self.avatar, api_key=lipsync_api_key)
        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config,
            api_key=subtitles_api_key,
        )
        self.video_gen = VideoGenerator(video_template=shorts_config.video_template)

        self.video_template = shorts_config.video_template

    async def generate_short_async(
        self,
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

        results = await asyncio.gather(*tasks)

        # Map results back
        idx = 0
        if AssetType.LIPSYNC in required_assets:
            template_assets.lipsync_video = results[idx]
            idx += 1
        if AssetType.SUBTITLES in required_assets:
            template_assets.subtitles = results[idx]

        print("Generating final video...")
        return self.video_gen.compose(template_assets=template_assets)

    def generate_short(
        self,
        files: list[str] | None = None,
        user_input: str | None = None,
    ):
        asyncio.run(
            self.generate_short_async(
                files=files,
                user_input=user_input,
            ),
        )


"""
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
"""
