from typing import Optional, List
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


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Firebase UID
    email: Optional[str] = None
    credits: int = Field(default=10)

    series: List["ReelSeries"] = Relationship(back_populates="user")


class Avatar(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Store the full Pydantic model data as JSON
    data: dict = Field(sa_column=Column(JSON))

    def to_pydantic(self) -> PydanticAvatar:
        return PydanticAvatar(**self.data)


class VideoTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Store the full Pydantic model data as JSON
    data: dict = Field(sa_column=Column(JSON))

    def to_pydantic(self) -> PydanticVideoTemplate:
        return PydanticVideoTemplate(**self.data)


class ReelSeries(SQLModel, table=True):
    """
    Represents a generation job that produces one or more reels.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_column=Column(String))
    topic: Optional[str] = None

    user: User = Relationship(back_populates="series")
    reels: List["Reel"] = Relationship(back_populates="series", cascade_delete=True)


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

    series: ReelSeries = Relationship(back_populates="reels")


# Response Models
class ReelRead(SQLModel):
    id: int
    sequence_number: int
    status: JobStatus
    cloudflare_r2_url: Optional[str] = None
    local_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class ReelSeriesRead(SQLModel):
    id: int
    user_id: str
    created_at: datetime
    status: JobStatus
    topic: Optional[str] = None
    reels: List[ReelRead]


# Request Model for API
class GenerateRequest(SQLModel):
    template_name: str
    avatar_names: List[str]
    amount: int = 1
    input_text: Optional[str] = None
    files: Optional[List[str]] = None


class AddCreditsRequest(SQLModel):
    amount: int


class UploadResponse(SQLModel):
    filename: str
    url: str
    key: str


class GenerateResponse(SQLModel):
    message: str
    series_id: int
    remaining_credits: int


class AddCreditsResponse(SQLModel):
    message: str
    total_credits: int
