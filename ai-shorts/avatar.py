class Voice:
    def __init__(
        self,
        provider: str,
        voice_id: str | None = None,
        sample_url: str | None = None,
        sample_transcript: str | None = None,
    ):
        self.provider = provider
        self.voice_id = voice_id
        self.sample_url = sample_url
        self.sample_transcript = sample_transcript


class Avatar:
    def __init__(
        self,
        name: str,
        instructions: str,
        voice: Voice,
        lipsync_provider: str,
        face_url: str | None = None,
        face_video_url: str | None = None,
        pads: list[str] | None = None,
    ):
        self.name = name
        self.instructions = instructions
        self.face_url = face_url
        self.face_video_url = face_video_url
        self.voice = voice
        self.lipsync_provider = lipsync_provider
        self.pads = pads
