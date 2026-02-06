from aishorts.modules.video_edit.video_edit import VideoTemplate
from aishorts.modules.script.script import Reel
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.ffmpeg_providers import FFmpegProvider
import uuid


class VideoGenerator:

    def __init__(
        self, video_template: VideoTemplate, provider: str = "local_ffmpeg", **kwargs
    ):
        self.template_config = video_template.template_config
        edit_template = video_template.edit_template.lower()

        edit_cls = EditTemplate.get(edit_template)
        if not edit_cls:
            raise ValueError(f"Unknown video template class '{provider}'")

        self.edit = edit_cls(self.template_config, **kwargs)

        render_cls = FFmpegProvider.get(provider)
        if not render_cls:
            raise ValueError(f"Unknown video template class '{provider}'")

        self.render = render_cls(**kwargs)

    def compose(self, reel: Reel, **kwargs) -> str:
        cmd = self.edit.compose(reel=reel, **kwargs)
        return self.render.render(cmd, f"{uuid.uuid4()}.mp4")
