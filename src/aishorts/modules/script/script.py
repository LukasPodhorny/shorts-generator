from pydantic import BaseModel
from typing import List, Optional, Literal


from pydantic import BaseModel, Field
from typing import List, Optional, Literal


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


class DialogueBlock(BaseModel):
    type: Literal["dialogue"]
    avatar: str
    text: str
    media: Optional[Media] = None


class QuestionBlock(BaseModel):
    type: Literal["question"]
    avatar: str
    text: str
    answer: str
    answer_duration: float = 2.0
    thinking_duration: float = 5.0


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
