from typing import Union, Dict, Optional, List
from pydantic import BaseModel


class Voice(BaseModel):
    provider: str
    voice_id: Optional[str] = None
    sample_url: Optional[Union[str, Dict]] = None
    sample_transcript: Optional[str] = None


class Avatar(BaseModel):
    name: str
    instructions: str
    voice: Voice
    lipsync_provider: str
    face_url: Optional[Union[str, Dict]] = None
    face_video_url: Optional[Union[str, Dict]] = None
    static_face_path: Optional[str] = None
    static_face_url: Optional[Union[str, Dict]] = None
    pads: Optional[List[str]] = None
    a_cfg_scale: Optional[int] = 2
    e_cfg_scale: Optional[int] = 1
