from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal, ClassVar, Any, Dict, Union
from pydantic.json_schema import SkipJsonSchema
from openai.types.audio import TranscriptionVerbose
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
    SLIDES = "slides"
    STOCK_VIDEO = "stock_video"


class BlockType(str, Enum):
    DIALOGUE = "dialogue"
    QUESTION = "question"
    SONG = "song"


class Trigger(BaseModel):
    start_word_index: int
    end_word_index: int


class MediaBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger: Trigger


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


class SlideItem(BaseModel):
    heading: str = Field(min_length=1, max_length=64)
    body: str = Field(default="", max_length=160)


class ChartPoint(BaseModel):
    label: str = Field(min_length=1, max_length=36)
    value: float = Field(allow_inf_nan=False, ge=-1e12, le=1e12)
    x: Optional[float] = Field(default=None, allow_inf_nan=False, ge=-1e12, le=1e12)


class SlideMedia(MediaBase):
    """Declarative teaching graphic. No executable code or HTML from the LLM."""

    type: Literal["slide"]
    layout: Literal["title", "bullets", "process", "comparison", "chart", "quote", "metrics", "donut", "timeline", "spotlight", "line_chart", "proportion", "cycle"]
    title: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(default="", max_length=180)
    items: List[SlideItem] = Field(default_factory=list, max_length=5)
    chart: List[ChartPoint] = Field(default_factory=list, max_length=6)
    unit: str = Field(default="", max_length=24)
    x_unit: str = Field(default="", max_length=24)
    source: str = Field(default="", max_length=220,
                        description="Short source citation; required for charts. Use 'Illustrative example' for invented teaching data.")

    @model_validator(mode="after")
    def validate_layout(self):
        if self.layout in {"bullets", "process"} and not self.items:
            raise ValueError(f"{self.layout} slides require at least one item")
        if self.layout == "comparison" and len(self.items) != 2:
            raise ValueError("comparison slides require exactly two items")
        if self.layout == "chart" and (len(self.chart) < 2 or not self.source.strip()):
            raise ValueError("chart slides require at least two data points and a source")
        if self.layout == "line_chart" and (
            len(self.chart) < 2 or not self.source.strip()
            or any(point.x is None for point in self.chart)
            or any(a.x >= b.x for a, b in zip(self.chart, self.chart[1:]))
        ):
            raise ValueError("line charts need ordered numeric x values and a source")
        if self.layout == "metrics" and (not 1 <= len(self.items) <= 3 or not self.source.strip()
                                         or any(len(item.heading) > 16 or not item.body.strip() for item in self.items)):
            raise ValueError("metrics slides need 1-3 short values, labels, and a source")
        if self.layout == "donut" and (not 2 <= len(self.chart) <= 5 or not self.source.strip()
                                       or any(point.value <= 0 for point in self.chart)):
            raise ValueError("donut slides need 2-5 positive shares of one whole and a source")
        if self.layout == "proportion" and (not 2 <= len(self.chart) <= 5 or not self.source.strip()
                                            or any(point.value <= 0 for point in self.chart)):
            raise ValueError("proportion slides need 2-5 positive shares of one whole and a source")
        if self.layout == "timeline" and not 2 <= len(self.items) <= 4:
            raise ValueError("timeline slides need 2-4 chronological milestones")
        if self.layout == "cycle" and not 3 <= len(self.items) <= 4:
            raise ValueError("cycle slides need 3-4 connected stages")
        if self.layout == "quote" and not self.subtitle.strip():
            raise ValueError("quote slides require the quotation in subtitle")
        return self


class StockVideoMedia(MediaBase):
    type: Literal["stock_video"]
    keywords: str = Field(min_length=2, max_length=120,
                          description="Concrete stock footage search, in English. Describe a subject or activity, never a URL.")


Media = Union[ImageMedia, LatexMedia, ManimMedia, SlideMedia, StockVideoMedia]


class MediaAttribution(BaseModel):
    provider: str
    creator: str
    source_url: str
    license: str


class BlockAssets(BaseModel):
    """Generated assets associated with a block"""

    voice_filepath: Optional[str] = None
    voice_url: Optional[Union[str, dict]] = None
    lipsync_filepath: Optional[str] = None
    lipsync_url: Optional[Union[str, dict]] = None
    staticface_filepath: Optional[str] = None
    staticface_url: Optional[Union[str, dict]] = None
    # Word-level timestamps; typed so it round-trips through JSON checkpoints.
    subtitles: Optional[TranscriptionVerbose] = None
    question_filepath: Optional[str] = None
    question_url: Optional[Union[str, dict]] = None
    song_filepath: Optional[str] = None
    song_url: Optional[Union[str, dict]] = None

    # Maps MediaBase.id -> filepath/url
    media_map: Dict[str, str] = Field(default_factory=dict)
    media_url_map: Dict[str, Union[str, dict]] = Field(default_factory=dict)
    media_attributions: Dict[str, MediaAttribution] = Field(default_factory=dict)
    slide_viewport: Optional[tuple[int, int, int, int]] = None


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
        AssetType.SLIDES,
        AssetType.STOCK_VIDEO,
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
    typing_duration: float = 3.0
    thinking_duration: float = 5.0
    answer_duration: float = 2.0
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
Block = Union[DialogueBlock, QuestionBlock, SongBlock]


class Reel(BaseModel):
    """Represents a single reel/chapter in the series"""

    title: str = Field(
        description="Title of this reel/chapter (e.g., 'Chapter 1: Light Absorption')"
    )
    description: Optional[str] = Field(
        None, description="Brief description of what this reel covers"
    )
    thumbnail_prompt: Optional[str] = Field(
        None, description="Visual prompt for generating a thumbnail image for this reel"
    )
    thumbnail_url: Optional[str] = Field(
        None, description="URL of the generated thumbnail image for this reel"
    )
    blocks: List[Block] = Field(
        description="The dialogue blocks that make up this reel"
    )


class ReelSeries(BaseModel):
    """Container for multiple related reels that together explain a topic"""

    topic: str = Field(
        description="Overall topic being explained (e.g., 'Photosynthesis')"
    )
    thumbnail_prompt: Optional[str] = Field(
        None,
        description="Visual prompt for generating a thumbnail image for the series",
    )
    thumbnail_url: Optional[str] = Field(
        None, description="URL of the generated thumbnail image for the series"
    )
    reels: List[Reel] = Field(
        description="Ordered list of reels, each covering a chapter/segment of the topic"
    )


class ReelOutput(BaseModel):
    title: str
    description: Optional[str]
    local_path: str
    presigned_url: str
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None  # Format: "MM:SS" or "HH:MM:SS"


class ReelSeriesOutput(BaseModel):
    topic: str
    thumbnail_url: Optional[str] = None
    reels: List[ReelOutput]


# Rebuild models to resolve Union types for Pydantic V2
Reel.model_rebuild()
ReelSeries.model_rebuild()
DialogueBlock.model_rebuild()
QuestionBlock.model_rebuild()
SongBlock.model_rebuild()
