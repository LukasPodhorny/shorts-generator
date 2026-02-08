from pydantic import BaseModel, Field
from typing import List, Optional, Literal, ClassVar
from typing import List, Optional, Literal, ClassVar, Any
from pydantic.json_schema import SkipJsonSchema
from enum import Enum


class AssetType(Enum):
    SCRIPT = "script"
    VOICE = "voice"
    LIPSYNC = "lipsync"
    SUBTITLES = "subtitles"
    IMAGES = "images"
    LATEX = "latex"
    QUESTION = "question"
    STATICFACE = "staticface"


class Trigger(BaseModel):
    start_word_index: int
    end_word_index: int


class MediaBase(BaseModel):
    trigger: Optional[Trigger] = None


class ImageMedia(MediaBase):
    type: Literal["image"]
    keywords: str


class LatexMedia(MediaBase):
    type: Literal["latex"]
    code: str


Media = ImageMedia | LatexMedia


class BlockAssets(BaseModel):
    """Generated assets associated with a block"""

    voice_filepath: Optional[str] = None
    voice_url: Optional[str] = None
    lipsync_filepath: Optional[str] = None
    lipsync_url: Optional[str] = None
    staticface_filepath: Optional[str] = None
    staticface_url: Optional[str] = None
    image_filepath: Optional[str] = None
    image_url: Optional[str] = None
    latex_filepath: Optional[str] = None
    latex_url: Optional[str] = None
    subtitles: Optional[Any] = None
    question_filepath: Optional[str] = None


class DialogueBlock(BaseModel):
    type: Literal["dialogue"]
    valid_assets: ClassVar[List[AssetType]] = [
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
        AssetType.STATICFACE,
    ]
    avatar: str
    text: str
    media: Optional[Media] = None
    assets: SkipJsonSchema[BlockAssets] = Field(default_factory=BlockAssets)


class QuestionBlock(BaseModel):
    type: Literal["question"]
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


# A Block can now be one of several types, distinguished by the `type` field.
# Pydantic uses this "discriminated union" to automatically parse the correct data model.
Block = DialogueBlock | QuestionBlock


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
