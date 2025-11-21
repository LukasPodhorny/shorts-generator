from pydantic import BaseModel, field_validator
from typing import List, Optional, Literal


class Trigger(BaseModel):
    start_index: int
    end_index: Optional[int] = None
    duration_seconds: Optional[float] = None

    @field_validator("end_index", "duration_seconds", mode="after")
    def validate_trigger(cls, v, values):
        # Require exactly one secondary timing method
        if not values.get("end_index") and not values.get("duration_seconds"):
            raise ValueError(
                "Trigger must include either end_index or duration_seconds."
            )
        if values.get("end_index") and values.get("duration_seconds"):
            raise ValueError("Trigger cannot have both end_index and duration_seconds.")
        return v


class Media(BaseModel):
    type: Literal["image", "latex"]
    keywords: Optional[str] = None  # for images
    code: Optional[str] = None  # for LaTeX
    trigger: Optional[Trigger] = None  # if missing → full block duration


class Block(BaseModel):
    type: Literal["dialogue"]
    avatar: str
    text: str
    media: List[Media] = []


class Script(BaseModel):
    script: List[Block]
