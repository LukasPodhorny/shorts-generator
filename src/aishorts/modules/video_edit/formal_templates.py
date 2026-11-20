"""Narration-led templates with a shared, bounded FFmpeg scene compositor."""

import math
from pathlib import Path

from openai.types.audio import TranscriptionVerbose, TranscriptionWord

from aishorts.modules.script.script import AssetType, BlockType, SlideMedia
from aishorts.modules.slides.style import PALETTES, PresentationStyle, SlideRenderConfig, legacy_visual_region
from aishorts.modules.video_edit.video_edit import EditTemplate, FilterGraph, SubtitleStyle, resolve_media_url


def asset_ref(path, url=None):
    if path and Path(path).is_file():
        return path
    if url:
        return resolve_media_url(url)
    raise ValueError(f"Missing rendered asset: {path or 'no path or URL'}")


def visual_changeover(block, media, duration):
    index = media.trigger.start_word_index
    count = max(1, len(block.text.split()))
    words = block.assets.subtitles.words if block.assets.subtitles else []
    timestamp = duration * index / count if 0 < index < count else duration / 2
    if words and len(words) == count and 0 < index < count:
        aligned = words[index].start
        if math.isfinite(aligned) and 0 < aligned < duration:
            timestamp = aligned
    return min(duration - 1 / 30, max(1 / 30, round(timestamp * 30) / 30))


class FormalTemplate(EditTemplate):
    core_assets = [AssetType.SCRIPT, AssetType.VOICE, AssetType.SUBTITLES, AssetType.SLIDES, AssetType.IMAGES, AssetType.LATEX]
    tag_assets = {AssetType.MANIM: False, AssetType.STOCK_VIDEO: False}
    allowed_blocks = [BlockType.DIALOGUE]
    width, height = 1920, 1080
    mode = "lecture"
    script_instructions_resource = "formal_instructions.txt"
    default_style = PresentationStyle()

    def __init__(self, template_config, **kwargs):
        self.style = template_config.presentation_style or self.default_style.model_copy()
        self.music = template_config.music
        self.render_config = SlideRenderConfig(width=self.width, height=self.height, mode=self.mode, style=self.style)

    def _get_block_segment(self, block):
        if block.type != BlockType.DIALOGUE:
            raise ValueError("Formal templates accept dialogue narration only")
        audio = asset_ref(block.assets.voice_filepath, block.assets.voice_url)
        duration = (self.get_video_duration(audio) if isinstance(audio, str)
                    else block.assets.subtitles.duration if block.assets.subtitles else 0)
        if not math.isfinite(duration) or not 0 < duration <= 180:
            raise ValueError("Each formal narration scene must have 0-180 seconds of audio")
        # Round up to a video frame and pad the audio to exactly the same boundary.
        duration = math.ceil(duration * 30) / 30
        slides = [m for m in block.media if isinstance(m, SlideMedia)]
        if len(slides) != 1:
            raise ValueError("Formal narration scenes require exactly one slide")
        slide = slides[0]
        return {"audio": audio, "duration": duration, "video": asset_ref(
            block.assets.media_map.get(slide.id), block.assets.media_url_map.get(slide.id)
        )}

    def compose(self, reel, **kwargs):
        if not 1 <= len(reel.blocks) <= 32:
            raise ValueError("Formal videos require 1-32 narration scenes")
        graph = FilterGraph()
        video_nodes, audio_nodes, captions = [], [], []
        total = 0.0
        for index, block in enumerate(reel.blocks):
            seg = self._get_block_segment(block)
            duration = seg["duration"]
            canvas, _ = graph.add_input(seg["video"], f"slide_{index}")
            canvas = (canvas.filter("loop", loop=-1, size=1, start=0)
                      .filter("fps", fps=30)
                      .filter("setpts", "PTS-STARTPTS").filter("setsar", 1)
                      .filter("format", "yuv420p"))
            visuals = sorted(
                (m for m in block.media if m.type != "slide" and (
                    block.assets.media_map.get(m.id) or block.assets.media_url_map.get(m.id)
                )),
                key=lambda m: m.trigger.start_word_index,
            )
            # Stretch the surviving visual across the scene if an optional lookup
            # failed. With two visuals, switch on the same frame for both.
            if duration < 2 / 30:
                visuals = visuals[:1]
            boundaries = [0.0]
            if len(visuals) == 2:
                boundaries.append(visual_changeover(block, visuals[1], duration))
            boundaries.append(duration)
            viewport = block.assets.slide_viewport or legacy_visual_region(self.mode)
            for media, start, end in zip(visuals, boundaries, boundaries[1:]):
                path = asset_ref(block.assets.media_map.get(media.id), block.assets.media_url_map.get(media.id))
                visual, _ = graph.add_input(path, f"visual_{index}_{media.type}")
                x, y, w, h = viewport
                if media.type in {"stock_video", "manim"}:
                    visual = visual.filter("setpts", "PTS-STARTPTS").filter("fps", fps=30)
                    visual = visual.filter("tpad", stop_mode="clone", stop_duration=end - start)
                else:
                    visual = visual.filter("loop", loop=-1, size=1, start=0).filter("fps", fps=30)
                visual = visual.filter("trim", duration=end - start)
                if media.type in {"image", "stock_video"}:
                    visual = visual.filter("scale", f"{w}:{h}", force_original_aspect_ratio="increase").filter("crop", f"{w}:{h}")
                else:
                    # Fit equations and teaching animations without cutting off labels.
                    color = PALETTES[self.style.theme]["panel"].replace("#", "0x")
                    visual = visual.filter("scale", f"{w}:{h}", force_original_aspect_ratio="decrease").filter(
                        "pad", f"{w}:{h}:(ow-iw)/2:(oh-ih)/2:color={color}")
                visual = visual.filter("setsar", 1).filter("setpts", f"PTS-STARTPTS+{start}/TB")
                canvas = graph.add_raw([canvas, visual], f"overlay=x={x}:y={y}:enable='gte(t,{start})*lt(t,{end})':eof_action=pass")
            # Trim AFTER overlay framesync. Trimming both overlay inputs at the
            # same instant can stall FFmpeg waiting for a final frame at EOF.
            # The infinite slide clock guarantees a frame that ends each scene.
            canvas = canvas.filter("trim", duration=duration)
            _, audio = graph.add_input(seg["audio"], f"narration_{index}")
            audio = (audio.filter("aresample", 48000).filter("aformat", channel_layouts="stereo")
                     .filter("apad").filter("atrim", duration=duration).filter("asetpts", "PTS-STARTPTS"))
            video_nodes.append(canvas)
            audio_nodes.append(audio)
            transcription = block.assets.subtitles
            if transcription and transcription.words:
                captions.extend(TranscriptionWord(word=word.word.replace("\\", " ").replace("{", "(").replace("}", ")"), start=total + max(0, word.start),
                                                   end=total + min(duration, word.end))
                                for word in transcription.words if word.start < duration and word.end > word.start)
            total += duration

        main = graph.add_raw(video_nodes, f"concat=n={len(video_nodes)}:v=1:a=0") if len(video_nodes) > 1 else video_nodes[0]
        audio = graph.add_raw(audio_nodes, f"concat=n={len(audio_nodes)}:v=0:a=1") if len(audio_nodes) > 1 else audio_nodes[0]
        audio = audio.filter("dynaudnorm", f=500, g=31, p=0.95, m=4, r=0.1).filter("aresample", 48000)
        if self.style.show_captions and captions:
            style = SubtitleStyle(font="DejaVu Sans", font_size=38 if self.width > self.height else 44,
                                  color="&H00FFFFFF", boxed=True, stroke_color="&H38130F0B",
                                  stroke_width=12, shadow_offset=0, alignment=2,
                                  offset_y=32 if self.width > self.height else 94,
                                  max_chars_per_line=84 if self.width > self.height else 38, remove_chars="")
            transcription = TranscriptionVerbose(duration=total, language="en", text="", words=captions)
            ass = self.transcription_to_ass(transcription, style, width=self.width, height=self.height)
            main = main.filter("ass", f"'{ass.download()}'")
        if self.music:
            music_ref = resolve_media_url(self.music) if isinstance(self.music, str) and self.music.startswith("https://") else self.music
            _, music = graph.add_input(music_ref, "background_music")
            music = (music.filter("aresample", 48000).filter("aformat", channel_layouts="stereo")
                     .filter("apad").filter("atrim", duration=total).filter("asetpts", "PTS-STARTPTS")
                     .filter("volume", self.style.music_volume).filter("afade", t="out", st=max(0, total - 1), d=1))
            audio = graph.add_raw([audio, music], "amix=inputs=2:duration=first:normalize=0").filter("alimiter", limit=0.95)
        return graph.build(main, audio, ["-t", str(total), "-r", "30", "-pix_fmt", "yuv420p",
                                         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"])


class LectureTemplate(FormalTemplate):
    provider_name = "lecture"
    description = "16:9 narrated lesson with clean slides, processes, comparisons and cited charts. Best for courses, academic explanations and workplace training. No visible avatar."


class DocumentaryTemplate(FormalTemplate):
    provider_name = "documentary"
    mode = "documentary"
    description = "16:9 documentary explainer with stock footage beside concise teaching notes. Best for science, history, geography and real-world processes. No visible avatar. Falls back to slides when footage is unavailable."
    tag_assets = {**FormalTemplate.tag_assets, AssetType.STOCK_VIDEO: True}
    default_style = PresentationStyle(theme="linen", accent_color="#17645D")


class BriefingTemplate(FormalTemplate):
    provider_name = "briefing"
    mode = "briefing"
    width, height = 1080, 1920
    description = "9:16 formal mobile briefing with photos, diagrams and large readable notes. Best for revision, professional social videos and concise explainers. No visible avatar."
    default_style = PresentationStyle(theme="slate", accent_color="#B4DE8C")
