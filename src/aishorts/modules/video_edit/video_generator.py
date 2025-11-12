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
