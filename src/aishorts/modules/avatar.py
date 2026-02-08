from dataclasses import dataclass
from pydantic import BaseModel


class Voice(BaseModel):
    provider: str
    voice_id: str | None = None
    sample_url: str | None = None
    sample_transcript: str | None = None


class Avatar(BaseModel):
    name: str
    instructions: str
    voice: Voice
    lipsync_provider: str
    face_url: str | None = None
    face_video_url: str | None = None
    static_face_path: str | None = None
    pads: list[str] | None = None
    a_cfg_scale: int | None = 2
    e_cfg_scale: int | None = 1
