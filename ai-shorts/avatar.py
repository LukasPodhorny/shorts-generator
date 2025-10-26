class Avatar:
    def __init__(
        self,
        name: str,
        instructions: str,
        voice_sample_url: str,
        face_url: str,
        voice_sample_transcript: str | None = None,
    ):
        self.name = name
        self.instructions = instructions
        self.voice_sample_url = voice_sample_url
        self.voice_sample_transcript = voice_sample_transcript
        self.face_url = face_url
