from aishorts.modules.video_edit.video_edit import (
    EditTemplate,
    TemplateConfig,
    TemplateAssets,
    AssetType,
    FFmpegCommand,
)


class GameplayTemplate(EditTemplate):
    provider_name = "gameplay"
    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
    ]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.music = template_config.music
        self.subtitle_style = template_config.subtitle_style

    def compose(self, template_assets: TemplateAssets) -> FFmpegCommand:

        # Calculate total duration
        total_duration = sum(
            self.get_video_duration(vid.filepath)
            for vid in template_assets.lipsync_videos
        )

        absolute_subtitles = self.convert_to_absolute_timing(template_assets.subtitles)
        final_subtitles = self.merge_transcriptions(absolute_subtitles)

        # Generate subtitles file
        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        # Build ordered input list
        inputs = []
        labels = []

        # Add all lipsync videos first (indices 0, 1, 2, ...)
        for i, lipsync_vid in enumerate(template_assets.lipsync_videos):
            inputs.append(lipsync_vid.filepath)
            labels.append(f"lipsync_{i}")

        # Add background video (index = len(lipsync_videos))
        bg_idx = len(inputs)
        inputs.append(self.bg_video)
        labels.append("bg_video")

        # Add music if present (index = len(lipsync_videos) + 1)
        music_idx = None
        if self.music is not None:
            music_idx = len(inputs)
            inputs.append(self.music)
            labels.append("music")

        # Build filter graph using actual indices
        filter_parts = []

        # Scale and crop each lipsync video
        num_lipsyncs = len(template_assets.lipsync_videos)
        for i in range(num_lipsyncs):
            filter_parts.append(
                f"[{i}:v] scale=1080:-1, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [lip{i}];"
            )

        # Concatenate all lipsync videos
        concat_inputs = "".join(f"[lip{i}]" for i in range(num_lipsyncs))
        filter_parts.append(
            f"{concat_inputs} concat=n={num_lipsyncs}:v=1:a=0 [lip_concat];"
        )

        # Audio concatenation
        for i in range(num_lipsyncs):
            filter_parts.append(f"[{i}:a] volume=5.0 [voice{i}];")

        concat_audio = "".join(f"[voice{i}]" for i in range(num_lipsyncs))
        filter_parts.append(f"{concat_audio} concat=n={num_lipsyncs}:v=0:a=1 [voice];")

        # Background video
        filter_parts.append(
            f"[{bg_idx}:v] trim=end={total_duration}, setpts=PTS-STARTPTS, "
            f"crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [game];"
        )

        # Stack lip and game
        filter_parts.append("[lip_concat][game] vstack=inputs=2 [stacked];")

        # Add subtitles
        filter_parts.append(f"[stacked] ass='{subs_path}' [video];")

        # Handle music
        if music_idx is not None:
            filter_parts.append(
                f"[{music_idx}:a] atrim=end={total_duration}, asetpts=PTS-STARTPTS, volume=0.2 [music];"
            )
            filter_parts.append("[voice][music] amix=inputs=2:normalize=0 [audio]")
        else:
            filter_parts.append("[voice] acopy [audio]")

        filter_graph = "".join(filter_parts)

        # Build command arguments (everything except inputs)
        args = [
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-c:v",
            self.video_codec,
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-r",
            "30",
        ]

        return FFmpegCommand(inputs=inputs, args=args, input_labels=labels)


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

        # Build ordered input list
        inputs = []
        labels = []

        # Add all lipsync videos first (indices 0, 1, 2, ...)
        for i, lipsync_vid in enumerate(template_assets.lipsync_videos):
            inputs.append(lipsync_vid.filepath)
            labels.append(f"lipsync_{i}")

        # Add background video (index = len(lipsync_videos))
        bg_idx = len(inputs)
        inputs.append(self.bg_video)
        labels.append("bg_video")

        # Add media files as inputs
        media_start_idx = len(inputs)
        for i, media in enumerate(media_timings):
            inputs.append(media.filepath)
            labels.append(f"media_{i}")

        # Add music if present (index = len(lipsync_videos) + 1 + num_media)
        music_idx = None
        if self.music is not None:
            music_idx = len(inputs)
            inputs.append(self.music)
            labels.append("music")

        # Build filter graph using actual indices
        filter_parts = []

        # Remove green screen and scale each lipsync video
        num_lipsyncs = len(template_assets.lipsync_videos)
        for i in range(num_lipsyncs):
            filter_parts.append(
                # f"[{i}:v] chromakey=0x00FF00:0.2:0.1, "
                f"[{i}:v] chromakey={self.chromakey_color}:{self.chromakey_similarity}:{self.chromakey_blend}, "
                f"scale=1080:1080 [lip{i}];"
            )

        # Concatenate all lipsync videos
        concat_inputs = "".join(f"[lip{i}]" for i in range(num_lipsyncs))
        filter_parts.append(
            f"{concat_inputs} concat=n={num_lipsyncs}:v=1:a=0 [lip_concat];"
        )

        # Audio concatenation
        for i in range(num_lipsyncs):
            filter_parts.append(f"[{i}:a] volume=5.0 [voice{i}];")

        concat_audio = "".join(f"[voice{i}]" for i in range(num_lipsyncs))
        filter_parts.append(f"{concat_audio} concat=n={num_lipsyncs}:v=0:a=1 [voice];")

        # Scale background video to PORTRAIT 1080x1920
        filter_parts.append(
            f"[{bg_idx}:v] trim=end={total_duration}, setpts=PTS-STARTPTS, "
            f"scale=1080:1920:force_original_aspect_ratio=increase, crop=1080:1920 [game];"
        )

        # Overlay lipsync at bottom center (flush with bottom edge)
        # x=(W-w)/2 centers horizontally: (1080-1080)/2 = 0
        # y=H-h positions at bottom with no padding: 1920-1080 = 840
        filter_parts.append("[game][lip_concat] overlay=x=(W-w)/2:y=H-h [stacked];")

        # Process and overlay each media (image/latex) at specific times
        current_label = "[stacked]"
        for i, media in enumerate(media_timings):
            next_label = f"[overlay{i}]"

            # Animation: Slide from Left (0.4s duration)
            # Start X: -w (off-screen left)
            # End X: (W-w)/2 (center)
            # Logic: -w + (TotalDistance) * Progress
            # TotalDistance = (W-w)/2 - (-w) = (W+w)/2
            anim_dur = 0.4
            x_expr = f"-w + ((W+w)/2) * min((t-{media.start_time})/{anim_dur}, 1)"

            filter_parts.append(
                f"{current_label}[media{i}] overlay=x='{x_expr}':y=100:"
                f"enable='between(t,{media.start_time},{media.end_time})' {next_label};"
            )

            current_label = next_label

        # If no media, current_label is still "[stacked]"
        subtitle_input = current_label

        # Add subtitles
        filter_parts.append(f"{subtitle_input} ass='{subs_path}' [video];")

        # Handle music
        if music_idx is not None:
            filter_parts.append(
                f"[{music_idx}:a] atrim=end={total_duration}, asetpts=PTS-STARTPTS, volume=0.2 [music];"
            )
            filter_parts.append("[voice][music] amix=inputs=2:normalize=0 [audio]")
        else:
            filter_parts.append("[voice] acopy [audio]")

        filter_graph = "".join(filter_parts)

        # Build command arguments (everything except inputs)
        args = [
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-c:v",
            self.video_codec,
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-r",
            "30",
        ]

        return FFmpegCommand(inputs=inputs, args=args, input_labels=labels)
