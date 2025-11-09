from aishorts.utils.registry import EDIT_TEMPLATES
from aishorts.modules.video_edit.video_edit import (
    TemplateAssets,
    TemplateConfig,
    VideoTemplate,
)
from aishorts.tests.sub_test import TEST_SUBTITLES_FORCED_ALIGNMENT
from aishorts.modules.video_edit.video_edit import SubtitleStyle


class VideoGenerator:

    def __init__(self, video_template: VideoTemplate, **kwargs):
        self.template_config = video_template.template_config
        provider = video_template.edit_template.lower()

        cls = EDIT_TEMPLATES.get(provider)
        if not cls:
            raise ValueError(f"Unknown Lipsync provider '{provider}'")

        self.edit = cls(self.template_config, **kwargs)

    def compose(self, template_assets: TemplateAssets, **kwargs) -> str:
        return self.edit.compose(template_assets=template_assets, **kwargs)


# Example usage
if __name__ == "__main__":
    assets = TemplateAssets(
        lipsync_video="output/lipsync/b7ab285994464d9dbfc62d485427f2f1.mp4",
        subtitles=TEST_SUBTITLES_FORCED_ALIGNMENT,
    )
    config = TemplateConfig(
        bg_video="assets/bg_video/gameplay_20.mp4",
        music="assets/music/music_20.mp3",
        subtitle_style=SubtitleStyle(font="assets/fonts/NotoSans-Bold.ttf"),
    )
    video_generator = VideoGenerator(
        VideoTemplate(edit_template="gameplay", template_config=config)
    )
    video_generator.compose(template_assets=assets)
