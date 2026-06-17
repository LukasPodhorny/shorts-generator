from aishorts.modules.video_edit.video_edit import (
    EditTemplate,
    TemplateConfig,
    FFmpegCommand,
    FilterGraph,
    resolve_media_url,
)
from aishorts.modules.script.script import Reel
from aishorts.modules.script.script import AssetType
from aishorts.modules.script.script import BlockType
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Encoder args shared by every gameplay-style template.
_GAMEPLAY_EXTRA_ARGS = ["-preset", "fast", "-c:a", "aac", "-r", "30"]


def _segment_duration(template: EditTemplate, block, video_path, audio_path) -> float:
    """Resolve a segment's duration: ffprobe -> subtitles -> question phase durations.

    Used by the gameplay-style templates. `video_path`/`audio_path` may be a local
    path or a dict URL; only local files can be probed.
    """
    probe_target = video_path
    try:
        duration = (
            template.get_video_duration(probe_target)
            if isinstance(probe_target, (str, Path)) and os.path.exists(probe_target)
            else 0.0
        )
    except Exception:
        duration = 0.0

    if duration == 0:
        if block.assets and block.assets.subtitles:
            duration = block.assets.subtitles.duration
        elif block.type == "question":
            # Use stored typing_duration from the question provider if available,
            # otherwise estimate it from the voiceover length.
            typing_dur = getattr(block, "typing_duration", 3.0)
            if typing_dur == 3.0 and audio_path and os.path.exists(audio_path):
                try:
                    typing_dur = template.get_video_duration(audio_path)
                except Exception:
                    pass
            duration = (
                typing_dur
                + getattr(block, "thinking_duration", 5.0)
                + getattr(block, "answer_duration", 2.0)
                + 3.0
            )
    return duration


class GameplayBaseTemplate(EditTemplate):
    """Shared config + segment resolution for the lipsync gameplay templates.

    Subclasses differ only in how each avatar/question segment's *video* is scaled
    and positioned on the canvas (top square vs. chroma-keyed bottom composite);
    everything else (segment audio, concat, background, media overlays, music,
    subtitles) comes from the base class helpers.
    """

    allowed_blocks = [BlockType.DIALOGUE, BlockType.QUESTION]

    def __init__(self, template_config: TemplateConfig, **kwargs):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style
        self.chromakey_color = template_config.chromakey_color
        self.chromakey_similarity = template_config.chromakey_similarity
        self.chromakey_blend = template_config.chromakey_blend
        self.manim_width = template_config.manim_width
        self.manim_style = template_config.manim_style

    def _get_block_segment(self, block):
        video_path = None
        audio_path = None
        seg_type = "none"

        if block.type == "dialogue" and block.assets:
            if block.assets.lipsync_filepath:
                seg_type = "video"
                video_path = block.assets.lipsync_filepath
                if not os.path.exists(video_path) and block.assets.lipsync_url:
                    video_path = resolve_media_url(block.assets.lipsync_url)
            elif block.assets.voice_filepath or block.assets.voice_url:
                # No lipsync: fall back to static face + voice audio.
                static_path = block.assets.staticface_filepath
                if not static_path or (
                    isinstance(static_path, str) and not os.path.exists(static_path)
                ):
                    static_path = resolve_media_url(block.assets.staticface_url)

                if static_path:
                    seg_type = "static_face"
                    video_path = static_path
                    audio_path = block.assets.voice_filepath
                    if (
                        audio_path
                        and not os.path.exists(audio_path)
                        and block.assets.voice_url
                    ):
                        audio_path = resolve_media_url(block.assets.voice_url)

        elif block.type == "question" and block.assets:
            if block.assets.question_filepath:
                seg_type = "question"
                video_path = block.assets.question_filepath
                if not os.path.exists(video_path) and block.assets.question_url:
                    video_path = resolve_media_url(block.assets.question_url)

                audio_path = block.assets.voice_filepath
                if (
                    audio_path
                    and not os.path.exists(audio_path)
                    and block.assets.voice_url
                ):
                    audio_path = resolve_media_url(block.assets.voice_url)

        if seg_type != "none" and video_path:
            return {
                "type": seg_type,
                "video": video_path,
                "audio": audio_path,
                "duration": _segment_duration(self, block, video_path, audio_path),
            }
        return None

    def _build_avatar_segments(self, graph, segments):
        """Build the per-segment (video, audio) node lists. Subclass-specific."""
        raise NotImplementedError

    def _overlay_avatar(self, graph, bg_v, lip_concat_v):
        """Composite the concatenated avatar video onto the background."""
        raise NotImplementedError

    def compose(self, reel: Reel, **kwargs) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
        )

        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style.model_copy(),
        ).download()

        graph = FilterGraph()

        lip_v_nodes, lip_a_nodes = self._build_avatar_segments(graph, segments)
        lip_concat_v, lip_concat_a = self._concat_av(graph, lip_v_nodes, lip_a_nodes)

        bg_v = self._build_background(graph, current_time)
        main_v = self._overlay_avatar(graph, bg_v, lip_concat_v)
        main_v = self._overlay_media(graph, main_v, media_timings)

        main_v = main_v.filter("ass", f"'{subs_path}'")
        main_v = main_v.filter("trim", duration=current_time)

        final_audio = self._mix_music(graph, lip_concat_a, current_time)

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=_GAMEPLAY_EXTRA_ARGS,
        )


class GameplayTemplate(GameplayBaseTemplate):

    provider_name = "gameplay"

    core_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    tag_assets = {
        AssetType.MANIM: True,
        AssetType.QUESTION: True,
    }

    media_fade_easing = "ease_in_out_quart"

    def _build_avatar_segments(self, graph, segments):
        lip_v_nodes = []
        lip_a_nodes = []

        for i, seg in enumerate(segments):
            if seg["type"] == "video":
                v, a = graph.add_input(seg["video"], f"seg_{i}")
                v = v.filter("fps", fps=30)
                # Scale to square
                v = v.filter("scale", "1080:1080")

            elif seg["type"] == "static_face":
                # Static face image + voice audio (lipsync fallback)
                v, _ = graph.add_input(seg["video"], f"seg_{i}_img")
                v = v.filter("scale", "1080:1080:force_original_aspect_ratio=decrease")
                v = v.filter("pad", "1080:1080:-1:-1:color=black@0")
                v = v.filter("format", "yuva420p")
                # Loop the static image for the segment duration
                v = v.filter("loop", loop=-1, size=1, start=0)
                v = v.filter("fps", fps=30)
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")
                a = self._segment_audio(graph, seg, i)

            elif seg["type"] == "question":
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                v = v.filter("fps", fps=30)
                # Scale question to fit in the square area (with padding if needed)
                v = v.filter("scale", "1080:1080:force_original_aspect_ratio=decrease")
                # Key out the magenta background BEFORE pad so pad's black@0 is truly transparent
                v = v.filter("chromakey", color="0xFF00FF", similarity=0.22, blend=0.0)
                v = v.filter("pad", "1080:1080:-1:-1:color=black@0")
                v = v.filter("format", "yuva420p")
                # Trim to expected duration to prevent container metadata issues
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")
                a = self._segment_audio(graph, seg, i)

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        return lip_v_nodes, lip_a_nodes

    def _overlay_avatar(self, graph, bg_v, lip_concat_v):
        # Square avatar video pinned to the top, centered horizontally.
        return graph.add_raw(
            [bg_v, lip_concat_v], "overlay=x=(W-w)/2:y=0:shortest=1", "stacked"
        )


class AlphaGameplayTemplate(GameplayBaseTemplate):
    provider_name = "alpha_gameplay"

    core_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    tag_assets = {
        AssetType.MANIM: False,
        AssetType.QUESTION: False,
    }

    def _build_avatar_segments(self, graph, segments):
        lip_v_nodes = []
        lip_a_nodes = []

        for i, seg in enumerate(segments):
            if seg["type"] == "video":
                v, a = graph.add_input(seg["video"], f"seg_{i}")
                v = v.filter("fps", fps=30)

                # Alpha specific: chromakey the avatar out of its background.
                v = v.filter(
                    "chromakey",
                    self.chromakey_color,
                    self.chromakey_similarity,
                    self.chromakey_blend,
                )
                # Remove green spill (outline)
                v = v.filter("despill", type="green")
                # Scale to square
                v = v.filter("scale", "1080:1080")
                # Pad to full canvas (avatar at bottom): x=0, y=1920-1080=840
                v = v.filter("pad", "1080:1920:0:840:color=0x00000000")

            elif seg["type"] == "static_face":
                # Static face image + voice audio (lipsync fallback)
                v, _ = graph.add_input(seg["video"], f"seg_{i}_img")
                v = v.filter("scale", "1080:1080:force_original_aspect_ratio=decrease")
                v = v.filter("pad", "1080:1080:-1:-1:color=0x00000000")
                v = v.filter("format", "yuva420p")
                # Pad to full canvas like lipsync (avatar at bottom)
                v = v.filter("pad", "1080:1920:0:840:color=0x00000000")
                # Loop the static image for the segment duration
                v = v.filter("loop", loop=-1, size=1, start=0)
                v = v.filter("fps", fps=30)
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")
                a = self._segment_audio(graph, seg, i)

            elif seg["type"] == "question":
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                v = v.filter("fps", fps=30)
                # Scale question to fit width (1000px)
                v = v.filter("scale", "1000:-1")
                # Key out the magenta background BEFORE pad so pad's black@0 is truly transparent
                v = v.filter("chromakey", color="0xFF00FF", similarity=0.22, blend=0.0)
                v = v.filter("pad", "1080:1920:(ow-iw)/2:(oh-ih)/2-200:color=black@0")
                v = v.filter("format", "yuva420p")
                # Trim to expected duration to prevent container metadata issues
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")
                a = self._segment_audio(graph, seg, i)

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        return lip_v_nodes, lip_a_nodes

    def _overlay_avatar(self, graph, bg_v, lip_concat_v):
        # lip_concat_v is already full canvas (1080x1920) with transparency.
        return graph.add_raw([bg_v, lip_concat_v], "overlay=0:0:shortest=1", "stacked")


class StaticGameplayTemplate(EditTemplate):
    provider_name = "static_gameplay"

    core_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.STATICFACE,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    tag_assets = {
        AssetType.MANIM: False,
        AssetType.QUESTION: False,
    }

    allowed_blocks = [BlockType.DIALOGUE, BlockType.QUESTION]

    def __init__(self, template_config: TemplateConfig, **kwargs):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style
        self.manim_width = template_config.manim_width
        self.manim_style = template_config.manim_style

    def _get_block_segment(self, block):
        video_path = None
        audio_path = None
        seg_type = "none"
        duration = 0.0

        if block.type == "dialogue" and block.assets:
            if block.assets.staticface_filepath and block.assets.voice_filepath:
                seg_type = "static_face"
                video_path = block.assets.staticface_filepath
                audio_path = block.assets.voice_filepath

                # Check for URLs if files missing
                if not os.path.exists(video_path) and block.assets.staticface_url:
                    video_path = resolve_media_url(block.assets.staticface_url)
                if not os.path.exists(audio_path) and block.assets.voice_url:
                    audio_path = resolve_media_url(block.assets.voice_url)

                try:
                    duration = (
                        self.get_video_duration(audio_path)
                        if isinstance(audio_path, (str, Path))
                        and os.path.exists(audio_path)
                        else 0.0
                    )
                except Exception:
                    duration = 0.0

                if duration == 0 and block.assets.subtitles:
                    duration = block.assets.subtitles.duration

        elif block.type == "question" and block.assets:
            if block.assets.question_filepath:
                seg_type = "question"
                video_path = block.assets.question_filepath
                audio_path = block.assets.voice_filepath

                if not os.path.exists(video_path) and block.assets.question_url:
                    video_path = resolve_media_url(block.assets.question_url)
                if (
                    audio_path
                    and not os.path.exists(audio_path)
                    and block.assets.voice_url
                ):
                    audio_path = resolve_media_url(block.assets.voice_url)

                duration = _segment_duration(self, block, video_path, audio_path)

        if seg_type != "none":
            return {
                "type": seg_type,
                "video": video_path,
                "audio": audio_path,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel, **kwargs) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
        )

        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style.model_copy(),
        ).download()

        graph = FilterGraph()

        lip_v_nodes = []
        lip_a_nodes = []

        for i, seg in enumerate(segments):
            if seg["type"] == "static_face":
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                _, a = graph.add_input(seg["audio"], f"seg_{i}_a")

                # Loop image, set fps, trim to audio duration
                v = v.filter("loop", loop=-1, size=1, start=0)
                v = v.filter("fps", fps=30)
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")

                # Scale and pad (avatar at bottom)
                v = v.filter("scale", "1080:1080")
                v = v.filter("pad", "1080:1920:0:840:color=0x00000000")
                v = v.filter("format", "yuva420p")

            elif seg["type"] == "question":
                # Same question handling as AlphaGameplayTemplate.
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                v = v.filter("fps", fps=30)
                v = v.filter("scale", "1000:-1")
                # Key out the magenta background BEFORE pad so pad's black@0 is truly transparent
                v = v.filter("chromakey", color="0xFF00FF", similarity=0.22, blend=0.0)
                v = v.filter("pad", "1080:1920:(ow-iw)/2:(oh-ih)/2-200:color=black@0")
                v = v.filter("format", "yuva420p")
                # Trim to expected duration to prevent container metadata issues
                v = v.filter("trim", duration=seg["duration"])
                v = v.filter("setpts", "PTS-STARTPTS")
                a = self._segment_audio(graph, seg, i)

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        lip_concat_v, lip_concat_a = self._concat_av(graph, lip_v_nodes, lip_a_nodes)

        bg_v = self._build_background(graph, current_time, apply_fps=False)
        main_v = graph.add_raw([bg_v, lip_concat_v], "overlay=0:0:shortest=1", "stacked")

        main_v = self._overlay_media(graph, main_v, media_timings)
        main_v = main_v.filter("ass", f"'{subs_path}'")

        final_audio = self._mix_music(graph, lip_concat_a, current_time)

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=_GAMEPLAY_EXTRA_ARGS,
        )


class SongTemplate(EditTemplate):
    provider_name = "song"

    core_assets = [
        AssetType.SCRIPT,
        AssetType.SONG,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    tag_assets = {
        AssetType.MANIM: True,
    }

    allowed_blocks = [BlockType.SONG]

    media_fade_easing = "ease_in_out_quart"

    def __init__(self, template_config: TemplateConfig, **kwargs):
        self.bg_video = template_config.bg_video
        self.subtitle_style = template_config.subtitle_style
        self.manim_width = template_config.manim_width
        self.manim_style = template_config.manim_style

    def _get_block_segment(self, block):
        if AssetType.SONG in block.valid_assets and block.assets:
            audio_path = block.assets.song_filepath
            if not audio_path:
                return None

            # Check for URL fallback
            if not os.path.exists(audio_path) and block.assets.song_url:
                audio_path = resolve_media_url(block.assets.song_url)

            try:
                duration = (
                    self.get_video_duration(audio_path)
                    if isinstance(audio_path, (str, Path))
                    and os.path.exists(audio_path)
                    else 0.0
                )
            except Exception:
                duration = 0.0

            if duration == 0 and block.assets.subtitles:
                duration = block.assets.subtitles.duration

            return {
                "type": "song",
                "audio": audio_path,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel, **kwargs) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
        )

        if current_time <= 0:
            raise ValueError(
                "Video duration is 0. Ensure the script contains valid Song blocks and song generation succeeded."
            )

        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        graph = FilterGraph()

        # 1. Process Audio (Songs)
        audio_nodes = []
        for i, seg in enumerate(segments):
            if seg["type"] == "song":
                _, a = graph.add_input(seg["audio"], f"seg_{i}_a")
                audio_nodes.append(a)

        if audio_nodes:
            final_audio = graph.add_raw(
                audio_nodes, f"concat=n={len(audio_nodes)}:v=0:a=1", "audio_concat"
            )
        else:
            final_audio = graph.add_raw(
                [], "anullsrc=channel_layout=stereo:sample_rate=44100", "silence"
            )

        # 2. Background + media overlays
        main_v = self._build_background(graph, current_time)
        main_v = self._overlay_media(graph, main_v, media_timings)

        # 3. Subtitles & final trim
        main_v = main_v.filter("ass", f"'{subs_path}'")
        main_v = main_v.filter("trim", duration=current_time)

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=_GAMEPLAY_EXTRA_ARGS,
        )
