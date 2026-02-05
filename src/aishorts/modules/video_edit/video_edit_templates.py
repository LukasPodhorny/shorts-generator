from aishorts.modules.video_edit.video_edit import (
    EditTemplate,
    TemplateConfig,
    TemplateAssets,
    FFmpegCommand,
    FilterGraph,
    Animator,
)
from aishorts.modules.script.script import AssetType
import os


class GameplayTemplate(EditTemplate):

    provider_name = "gameplay"

    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style
        self.chromakey_color = template_config.chromakey_color
        self.chromakey_similarity = template_config.chromakey_similarity
        self.chromakey_blend = template_config.chromakey_blend

    def compose(self, template_assets: TemplateAssets) -> FFmpegCommand:
        # Calculate total duration
        total_duration = sum(
            self.get_video_duration(vid.filepath)
            for vid in template_assets.lipsync_videos
        )

        absolute_subtitles = self.convert_to_absolute_timing(template_assets.subtitles)
        final_subtitles = self.merge_transcriptions(absolute_subtitles)

        # Extract media timings
        media_timings = self.extract_media_timings(
            blocks=template_assets.reel_script.blocks,
            absolute_subtitles=absolute_subtitles,
            images=template_assets.images,
            latex=template_assets.latex,
        )

        # Generate subtitles file
        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        # --- Build Filter Graph ---
        graph = FilterGraph()

        # 1. Process Lipsync Videos
        lip_v_nodes = []
        lip_a_nodes = []

        for i, lipsync_vid in enumerate(template_assets.lipsync_videos):
            v, a = graph.add_input(lipsync_vid.filepath, f"lipsync_{i}")
            # Scale to square
            v = v.filter("scale", "1080:1080")
            # Boost volume
            a = a.filter("volume", "5.0")

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        # Concat lipsyncs
        # (We use add_raw because concat takes a list of inputs and specific syntax)
        lip_concat_v = graph.add_raw(
            lip_v_nodes, f"concat=n={len(lip_v_nodes)}:v=1:a=0", "lip_concat_v"
        )
        lip_concat_a = graph.add_raw(
            lip_a_nodes, f"concat=n={len(lip_a_nodes)}:v=0:a=1", "lip_concat_a"
        )

        # 2. Process Background
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=total_duration).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        # 3. Overlay Lipsync on Background
        # overlay takes [background][foreground]
        main_v = graph.add_raw(
            [bg_v, lip_concat_v], "overlay=x=(W-w)/2:y=0:shortest=1", "stacked"
        )

        # 4. Media Overlays
        for i, media in enumerate(media_timings):
            # temporary for testing
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=media.end_time,
                duration=0.4,
                easing="ease_ease_in_out_quart",
            )

            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=media.end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
                easing="ease_in_out_quart",
            )

            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{media.end_time})':shortest=1",
            )

        # 5. Subtitles
        main_v = main_v.filter("ass", f"'{subs_path}'")

        # 6. Audio Mixing
        final_audio = lip_concat_a
        if self.music:
            _, music_a = graph.add_input(self.music, "music")
            music_a = (
                music_a.filter("atrim", end=total_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("volume", "0.2")
            )
            final_audio = graph.add_raw(
                [final_audio, music_a], "amix=inputs=2:normalize=0", "audio_mix"
            )

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=[
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-r",
                "30",
            ],
        )


class AlphaGameplayTemplate(EditTemplate):
    provider_name = "alpha_gameplay"

    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.LATEX,
    ]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style
        self.chromakey_color = template_config.chromakey_color
        self.chromakey_similarity = template_config.chromakey_similarity
        self.chromakey_blend = template_config.chromakey_blend

    def compose(self, template_assets: TemplateAssets) -> FFmpegCommand:
        # Calculate total duration
        total_duration = sum(
            self.get_video_duration(vid.filepath)
            for vid in template_assets.lipsync_videos
        )

        absolute_subtitles = self.convert_to_absolute_timing(template_assets.subtitles)
        final_subtitles = self.merge_transcriptions(absolute_subtitles)

        # Extract media timings
        media_timings = self.extract_media_timings(
            blocks=template_assets.reel_script.blocks,
            absolute_subtitles=absolute_subtitles,
            images=template_assets.images,
            latex=template_assets.latex,
        )

        # Generate subtitles file
        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        # --- Build Filter Graph ---
        graph = FilterGraph()

        # 1. Process Lipsync Videos
        lip_v_nodes = []
        lip_a_nodes = []

        for i, lipsync_vid in enumerate(template_assets.lipsync_videos):
            v, a = graph.add_input(lipsync_vid.filepath, f"lipsync_{i}")

            # Alpha specific: Chromakey
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

            # Boost volume
            a = a.filter("volume", "5.0")

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        # Concat lipsyncs
        lip_concat_v = graph.add_raw(
            lip_v_nodes, f"concat=n={len(lip_v_nodes)}:v=1:a=0", "lip_concat_v"
        )
        lip_concat_a = graph.add_raw(
            lip_a_nodes, f"concat=n={len(lip_a_nodes)}:v=0:a=1", "lip_concat_a"
        )

        # 2. Process Background
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=total_duration).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        # 3. Overlay Lipsync on Background
        # Alpha specific: y=H-h (bottom)
        main_v = graph.add_raw(
            [bg_v, lip_concat_v], "overlay=x=(W-w)/2:y=H-h:shortest=1", "stacked"
        )

        # 4. Media Overlays
        for i, media in enumerate(media_timings):
            # temporary for testing
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=media.end_time,
                duration=0.4,
            )

            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=media.end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
            )

            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{media.end_time})':shortest=1",
            )

        # 5. Subtitles
        main_v = main_v.filter("ass", f"'{subs_path}'")

        # 6. Audio Mixing
        final_audio = lip_concat_a
        if self.music:
            _, music_a = graph.add_input(self.music, "music")
            music_a = (
                music_a.filter("atrim", end=total_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("volume", "0.2")
            )
            final_audio = graph.add_raw(
                [final_audio, music_a], "amix=inputs=2:normalize=0", "audio_mix"
            )

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=[
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-r",
                "30",
            ],
        )
