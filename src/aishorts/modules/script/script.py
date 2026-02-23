from pydantic import BaseModel, Field
from typing import List, Optional, Literal, ClassVar, Any, Dict
from pydantic.json_schema import SkipJsonSchema
from enum import Enum
import uuid


class AssetType(Enum):
    SCRIPT = "script"
    VOICE = "voice"
    LIPSYNC = "lipsync"
    SUBTITLES = "subtitles"
    IMAGES = "images"
    LATEX = "latex"
    QUESTION = "question"
    STATICFACE = "staticface"
    MANIM = "manim"
    SONG = "song"


class BlockType(str, Enum):
    DIALOGUE = "dialogue"
    QUESTION = "question"
    SONG = "song"


class Trigger(BaseModel):
    start_word_index: int
    end_word_index: int


class MediaBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger: Optional[Trigger] = None


class ImageMedia(MediaBase):
    type: Literal["image"]
    keywords: str = Field(
        description="A single, complete sentence describing the visual scene. STRICT LIMIT: Under 10 words.",
        max_length=150,
    )


class LatexMedia(MediaBase):
    type: Literal["latex"]
    code: str


class ManimMedia(MediaBase):
    type: Literal["manim"]
    prompt: str


Media = ImageMedia | LatexMedia | ManimMedia


class BlockAssets(BaseModel):
    """Generated assets associated with a block"""

    voice_filepath: Optional[str] = None
    voice_url: Optional[str] = None
    lipsync_filepath: Optional[str] = None
    lipsync_url: Optional[str] = None
    staticface_filepath: Optional[str] = None
    staticface_url: Optional[str] = None
    subtitles: Optional[Any] = None
    question_filepath: Optional[str] = None
    song_filepath: Optional[str] = None
    song_url: Optional[str] = None

    # Maps MediaBase.id -> filepath/url
    media_map: Dict[str, str] = Field(default_factory=dict)
    media_url_map: Dict[str, str] = Field(default_factory=dict)


class DialogueBlock(BaseModel):
    type: Literal[BlockType.DIALOGUE]
    valid_assets: ClassVar[List[AssetType]] = [
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
        AssetType.STATICFACE,
        AssetType.MANIM,
    ]
    avatar: str
    text: str
    media: List[Media] = Field(default_factory=list)
    assets: SkipJsonSchema[BlockAssets] = Field(default_factory=BlockAssets)


class QuestionBlock(BaseModel):
    type: Literal[BlockType.QUESTION]
    valid_assets: ClassVar[List[AssetType]] = [
        AssetType.VOICE,
        AssetType.QUESTION,
    ]
    avatar: str
    text: str
    answer: str
    answer_duration: float = 2.0
    thinking_duration: float = 5.0
    assets: SkipJsonSchema[BlockAssets] = Field(default_factory=BlockAssets)


class SongBlock(BaseModel):
    type: Literal[BlockType.SONG]
    valid_assets: ClassVar[List[AssetType]] = [
        AssetType.SONG,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
        AssetType.STATICFACE,
        AssetType.MANIM,
    ]
    text: str
    media: List[Media] = Field(default_factory=list)
    assets: SkipJsonSchema[BlockAssets] = Field(default_factory=BlockAssets)


# A Block can now be one of several types, distinguished by the `type` field.
# Pydantic uses this "discriminated union" to automatically parse the correct data model.
Block = DialogueBlock | QuestionBlock | SongBlock


class Reel(BaseModel):
    """Represents a single reel/chapter in the series"""

    title: str = Field(
        description="Title of this reel/chapter (e.g., 'Chapter 1: Light Absorption')"
    )
    description: Optional[str] = Field(
        None, description="Brief description of what this reel covers"
    )
    blocks: List[Block] = Field(
        description="The dialogue blocks that make up this reel"
    )


class ReelSeries(BaseModel):
    """Container for multiple related reels that together explain a topic"""

    topic: str = Field(
        description="Overall topic being explained (e.g., 'Photosynthesis')"
    )
    reels: List[Reel] = Field(
        description="Ordered list of reels, each covering a chapter/segment of the topic"
    )


class Reel(BaseModel):
    """Represents a single reel/chapter in the series"""

    title: str = Field(
        description="Title of this reel/chapter (e.g., 'Chapter 1: Light Absorption')"
    )
    description: Optional[str] = Field(
        None, description="Brief description of what this reel covers"
    )
    blocks: List[Block] = Field(
        description="The dialogue blocks that make up this reel"
    )


class ReelSeries(BaseModel):
    """Container for multiple related reels that together explain a topic"""

    topic: str = Field(
        description="Overall topic being explained (e.g., 'Photosynthesis')"
    )
    reels: List[Reel] = Field(
        description="Ordered list of reels, each covering a chapter/segment of the topic"
    )


class ReelOutput(BaseModel):
    title: str
    description: Optional[str]
    local_path: str
    presigned_url: str


class ReelSeriesOutput(BaseModel):
    topic: str
    reels: List[ReelOutput]
