"""Shared geometry keeps rendered teaching graphics and video overlays aligned."""

from typing import Literal

from pydantic import BaseModel, Field


class PresentationStyle(BaseModel):
    theme: Literal["paper", "midnight", "slate", "linen"] = "paper"
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


def layout_regions(config: SlideRenderConfig, layout: str = "bullets"):
    """Return (content, visual) boxes as x, y, width, height, in output pixels."""
    opener = layout == "title"
    if config.mode == "briefing":
        if not config.has_visual:
            return (72, 356, 936, 1284), None
        if layout == "spotlight":
            return (72, 1000, 936, 620), (0, 108, 1080, 860)
        if opener:
            return (72, 152, 936, 410), (72, 610, 936, 1018)
        return (72, 950, 936, 690), (72, 356, 936, 548)
    if not config.has_visual:
        return (88, 306, 1744, 562), None
    if layout == "spotlight":
        return (88, 154, 790, 700), (974, 110, 946, 758)
    y = 150 if opener else 306
    height = 868 - y
    if config.mode == "documentary":
        return (1152, y, 680, height), (88, y, 1016, height)
    return (88, y, 808, height), (952, y, 880, height)


def legacy_visual_region(mode: str):
    """Placement for checkpoints that already contain a previous design's PNGs."""
    if mode == "briefing":
        return (72, 1040, 936, 540)
    if mode == "documentary":
        return (80, 300, 1080, 550)
    return (1010, 300, 830, 550)


PALETTES = {
    "paper": {"bg": "#F7F4EC", "wash": "#E8EDDF", "ink": "#142423", "muted": "#475A55", "panel": "#F9F7F1", "line": "#C9D2C8"},
    "midnight": {"bg": "#0C1921", "wash": "#172D36", "ink": "#F2F6F3", "muted": "#A7BDBF", "panel": "#152730", "line": "#36515B"},
    "slate": {"bg": "#111D19", "wash": "#22372A", "ink": "#F6F5E8", "muted": "#B5C7B5", "panel": "#1C2C25", "line": "#3D5548"},
    "linen": {"bg": "#F4EFE5", "wash": "#F4EFE5", "ink": "#182C33", "muted": "#48606A", "panel": "#E9E2D5", "line": "#B8C2BE"},
}
