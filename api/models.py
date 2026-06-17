from typing import Optional, List, Union, Literal
from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship, Column, JSON, String
from aishorts.modules.avatar import Avatar as PydanticAvatar
from aishorts.modules.video_edit.video_edit import (
    VideoTemplate as PydanticVideoTemplate,
)


class JobStatus(str, Enum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    DONE = "Done"
    FAILED = "Failed"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserBase(SQLModel):
    id: str
    email: Optional[str] = None
    credits: int


class UserRead(UserBase):
    stripe_customer_id: Optional[str] = None
    subscription_status: Optional[str] = None
    plan_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
    role: UserRole = UserRole.USER


class User(UserBase, table=True):
    id: str = Field(primary_key=True)  # Firebase UID
    email: Optional[str] = None
    credits: int = Field(default=90)
    role: UserRole = Field(default=UserRole.USER, sa_column=Column(String))

    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    stripe_subscription_id: Optional[str] = Field(default=None, index=True)
    subscription_status: Optional[str] = None
    plan_id: Optional[str] = None
    current_period_end: Optional[datetime] = None

    series: List["ReelSeries"] = Relationship(back_populates="user")
    uploads: List["UploadedFile"] = Relationship(back_populates="user")


class SubscriptionPlan(SQLModel, table=True):
    stripe_price_id: str = Field(primary_key=True)
    name: str
    credits: int
    description: Optional[str] = None


class Avatar(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Store the full Pydantic model data as JSON
    data: dict = Field(sa_column=Column(JSON))

    def to_pydantic(self) -> PydanticAvatar:
        return PydanticAvatar(**self.data)


class AvatarCreate(SQLModel):
    name: str
    data: dict


class VideoTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Store the full Pydantic model data as JSON
    data: dict = Field(sa_column=Column(JSON))
    credits: int = Field(default=1, description="Credits cost per reel")
    preview_url: Optional[str] = Field(default=None, description="Preview video URL or R2 key")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail image URL (first frame of preview)")

    def to_pydantic(self) -> PydanticVideoTemplate:
        return PydanticVideoTemplate(**self.data)


class VideoTemplateCreate(SQLModel):
    name: str
    data: dict


class VideoTemplateTag(SQLModel):
    """User-toggleable asset tag on a template."""
    asset_type: str
    default: bool


class VideoTemplateRead(SQLModel):
    """Response model for VideoTemplate with credits and preview"""
    id: int
    name: str
    credits: int
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    tags: List[VideoTemplateTag] = Field(default_factory=list)


class GenerationConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Stores provider/model config for all pipeline stages as JSON
    data: dict = Field(sa_column=Column(JSON))
    is_default: bool = Field(default=False)

    def to_config_kwargs(self) -> dict:
        """Returns kwargs that can be spread into ShortsConfig(avatars=..., video_template=..., **kwargs)."""
        from aishorts.shorts_generator import (
            ScriptConfig, FFmpegConfig, ManimConfig,
            ImagesConfig, LatexConfig, QuestionConfig, SongConfig,
        )
        from aishorts import SubtitleConfig

        config_map = {
            "script_config": ScriptConfig,
            "subtitle_config": SubtitleConfig,
            "ffmpeg_config": FFmpegConfig,
            "manim_config": ManimConfig,
            "images_config": ImagesConfig,
            "latex_config": LatexConfig,
            "question_config": QuestionConfig,
            "song_config": SongConfig,
        }

        kwargs = {}
        for key, cls in config_map.items():
            if key in self.data:
                kwargs[key] = cls(**self.data[key])
        return kwargs


class GenerationConfigCreate(SQLModel):
    name: str
    data: dict
    is_default: bool = False


class GenerationConfigRead(SQLModel):
    # Intentionally excludes `data`: it holds provider configuration
    # (endpoints, model settings, possibly credentials) and is served on a
    # public, unauthenticated endpoint.
    id: int
    name: str
    is_default: bool


class ReelSeries(SQLModel, table=True):
    """
    Represents a generation job that produces one or more reels.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_column=Column(String))
    topic: Optional[str] = None
    thumbnail_url: Optional[str] = None

    user: User = Relationship(back_populates="series")
    reels: List["Reel"] = Relationship(back_populates="series", cascade_delete=True, sa_relationship_kwargs={"order_by": "Reel.sequence_number"})


class Reel(SQLModel, table=True):
    """
    Represents an individual video file within a series.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    series_id: int = Field(foreign_key="reelseries.id")
    sequence_number: int
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_column=Column(String))
    cloudflare_r2_url: Optional[str] = None
    local_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None  # Video duration in "MM:SS" or "HH:MM:SS" format

    series: ReelSeries = Relationship(back_populates="reels")


class UploadedFileBase(SQLModel):
    filename: str
    url: str
    key: str
    content_type: str


class UploadedFile(UploadedFileBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="uploads")


# Response Models
class ReelRead(SQLModel):
    id: int
    sequence_number: int
    status: JobStatus
    cloudflare_r2_url: Optional[str] = None
    local_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None


class ReelSeriesRead(SQLModel):
    id: int
    user_id: str
    created_at: datetime
    status: JobStatus
    topic: Optional[str] = None
    thumbnail_url: Optional[str] = None
    reels: List[ReelRead]


class UploadedFileRead(UploadedFileBase):
    id: int
    created_at: datetime


# Request Model for API
class GenerateRequest(SQLModel):
    template_name: str
    avatar_names: List[str] = Field(max_length=4)
    amount: int = Field(default=1, ge=1, le=7)
    input_text: Optional[str] = None
    files: Optional[List[str]] = None
    # Web URLs used as source material (websites, YouTube videos, Wikipedia, ...)
    links: Optional[List[str]] = Field(default=None, max_length=10)
    config_name: Optional[str] = None  # If None, uses the default GenerationConfig
    # Asset-type string values the user wants enabled. None = use template defaults.
    enabled_tags: Optional[List[str]] = None


# --- Chatbot / intent-parse entry point (/api/plan) ---
# The chat UI tracks the text box and attachments separately, so the request
# body arrives already structured: the instruction in one field, the attached
# sources as their own labeled list. The parser is *told* which sources exist
# via this list; it never extracts file keys or links out of the prose.
class AttachedFile(SQLModel):
    type: Literal["file"] = "file"
    name: str
    key: str  # an UploadedFile key the user owns (supplied by the UI, not typed)


class AttachedLink(SQLModel):
    type: Literal["link"] = "link"
    url: str


class PlanRequest(SQLModel):
    # The freeform user message from the chat box.
    instruction: str
    # Sources the user attached through the UI (owned file keys and/or links).
    attachments: List[Union[AttachedFile, AttachedLink]] = Field(default_factory=list)
    # Explicit manual choices the user made in the UI. Any field set here is
    # final: the parser fills only what the user left unspecified.
    template_name: Optional[str] = None
    avatar_names: Optional[List[str]] = Field(default=None, max_length=4)
    amount: Optional[int] = Field(default=None, ge=1, le=7)
    enabled_tags: Optional[List[str]] = None
    config_name: Optional[str] = None


class AddCreditsRequest(SQLModel):
    amount: int


class GenerateResponse(SQLModel):
    message: str
    series_id: int
    remaining_credits: int


class AddCreditsResponse(SQLModel):
    message: str
    total_credits: int


class CreateCheckoutRequest(SQLModel):
    price_id: str


class CreateCheckoutResponse(SQLModel):
    url: str
