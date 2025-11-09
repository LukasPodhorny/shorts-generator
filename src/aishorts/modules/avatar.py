from dataclasses import dataclass


@dataclass
class Voice:
    provider: str
    voice_id: str | None = None
    sample_url: str | None = None
    sample_transcript: str | None = None


@dataclass
class Avatar:
    name: str
    instructions: str
    voice: Voice
    lipsync_provider: str
    face_url: str | None = None
    face_video_url: str | None = None
    pads: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict):
        data = {**data, "voice": Voice(**data["voice"])}
        return cls(**data)
