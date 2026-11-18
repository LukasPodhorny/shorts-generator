"""Shared geometry keeps rendered teaching graphics and video overlays aligned."""

from typing import Literal

from pydantic import BaseModel, Field


class PresentationStyle(BaseModel):
    theme: Literal["paper", "midnight", "slate"] = "paper"
    accent_color: str = Field(default="#087F8C", pattern=r"^#[0-9a-fA-F]{6}$")
    brand_name: str = Field(default="", max_length=48)
    show_captions: bool = True
    music_volume: float = Field(default=0.08, ge=0, le=0.3)


class SlideRenderConfig(BaseModel):
    width: Literal[1080, 1920] = 1920
    height: Literal[1080, 1920] = 1080
    mode: Literal["lecture", "documentary", "briefing"] = "lecture"
    style: PresentationStyle = Field(default_factory=PresentationStyle)
    has_visual: bool = False
    chapter: int = Field(default=1, ge=1, le=32)
    chapters: int = Field(default=1, ge=1, le=32)
    attribution: str = Field(default="", max_length=500)


def layout_regions(config: SlideRenderConfig):
    """Return (content, visual) boxes as x, y, width, height, in output pixels."""
    if config.mode == "briefing":
        return ((72, 470, 936, 500), (72, 1040, 936, 540)) if config.has_visual else (
            (72, 470, 936, 1100), None
        )
    if config.mode == "documentary" and config.has_visual:
        return (1240, 300, 600, 550), (80, 300, 1080, 550)
    if config.has_visual:
        return (80, 300, 850, 550), (1010, 300, 830, 550)
    return (80, 300, 1760, 550), None


PALETTES = {
    "paper": {"bg": "#F5F3ED", "ink": "#162B36", "muted": "#4C626B", "panel": "#E8E7DF", "line": "#CCD4D1"},
    "midnight": {"bg": "#101F2E", "ink": "#F3F5F7", "muted": "#B2C5D1", "panel": "#1D3245", "line": "#3F5668"},
    "slate": {"bg": "#182723", "ink": "#F5F3E9", "muted": "#B6C8BC", "panel": "#293D34", "line": "#496255"},
}
