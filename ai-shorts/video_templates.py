class TemplateAssets:
    def __init__(
        self,
        bg_video: str,
        voiceover: str,
        lipsync_video: str | None = None,
        music: str | None = None,
    ):
        self.bg_video = bg_video
        self.voiceover = voiceover
        self.lipsync_video = lipsync_video
        self.music = music

    """
    @classmethod
    def from_json(cls, path: str):
        import json
        with open(path, "r") as f:
            return cls(**json.load(f))
    """


class BaseTemplate:
    def __init__(self, name, template_assets: TemplateAssets):
        pass

    def compose(self):
        raise NotImplementedError("You must implement compose function.")


class TestTemplate(BaseTemplate):
    def __init__(self):
        super().__init__()
