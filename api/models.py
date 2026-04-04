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
    credits: int = Field(default=10)
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

    def to_pydantic(self) -> PydanticVideoTemplate:
        return PydanticVideoTemplate(**self.data)


class VideoTemplateCreate(SQLModel):
    name: str
    data: dict


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
    thumbnail_url: Optional[str] = None

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
    avatar_names: List[str]
    amount: int = 1
    input_text: Optional[str] = None
    files: Optional[List[str]] = None


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
