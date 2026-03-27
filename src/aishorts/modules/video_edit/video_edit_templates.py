from aishorts.modules.video_edit.video_edit import (
    EditTemplate,
    TemplateConfig,
    FFmpegCommand,
    FilterGraph,
    Animator,
)
from aishorts.modules.script.script import Reel
from aishorts.modules.script.script import AssetType
from aishorts.modules.script.script import BlockType
import os


class GameplayTemplate(EditTemplate):

    provider_name = "gameplay"

    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.MANIM,
        AssetType.LATEX,
        AssetType.QUESTION,
    ]

    allowed_blocks = [BlockType.DIALOGUE, BlockType.QUESTION]

    def __init__(self, template_config: TemplateConfig):
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

        if block.type == "dialogue" and block.assets and block.assets.lipsync_filepath:
            seg_type = "video"
            video_path = block.assets.lipsync_filepath
        elif (
            block.type == "question" and block.assets and block.assets.question_filepath
        ):
            seg_type = "question"
            video_path = block.assets.question_filepath
            audio_path = block.assets.voice_filepath

        if seg_type != "none":
            duration = self.get_video_duration(video_path)
            return {
                "type": seg_type,
                "video": video_path,
                "audio": audio_path,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
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

        for i, seg in enumerate(segments):
            if seg["type"] == "video":
                v, a = graph.add_input(seg["video"], f"seg_{i}")
                v = v.filter("fps", fps=30)
                # Scale to square
                v = v.filter("scale", "1080:1080")

            elif seg["type"] == "question":
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                # Scale question to fit in the square area (with padding if needed)
                v = v.filter("scale", "1080:1080:force_original_aspect_ratio=decrease")
                v = v.filter("pad", "1080:1080:-1:-1:color=0x00000000")

                # Generate silence of full video duration to ensure sync
                silence = graph.add_raw(
                    [],
                    f"anullsrc=channel_layout=stereo:sample_rate=44100:d={seg['duration']}",
                    f"silence_{i}",
                )

                if seg["audio"]:
                    _, a_in = graph.add_input(seg["audio"], f"seg_{i}_a")
                    # Mix voice with silence. amix averages volume (1/2), so we boost it back.
                    # duration=first ensures it matches the silence (video) duration.
                    a = graph.add_raw(
                        [silence, a_in],
                        "amix=inputs=2:duration=first:dropout_transition=0:normalize=0",
                        f"seg_{i}_mix",
                    )
                else:
                    a = silence

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

        # Normalize audio levels
        lip_concat_a = lip_concat_a.filter("loudnorm", I="-16", TP="-1.5", LRA="11")

        # 2. Process Background
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=current_time).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        # 3. Overlay Lipsync on Background
        # overlay takes [background][foreground]
        main_v = graph.add_raw(
            [bg_v, lip_concat_v], "overlay=x=(W-w)/2:y=0:shortest=1", "stacked"
        )

        # 4. Media Overlays
        # Note: Media timings are currently empty in this specific block because I didn't fully port the extraction logic
        # for GameplayTemplate. The user's main issue was AlphaGameplayTemplate.
        for i, media in enumerate(media_timings):
            # temporary for testing
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")

            display_end_time = media.end_time

            if media.media_type == "manim":
                # Manim is a video, scale to fit width and shift time
                manim_duration = self.get_video_duration(media.filepath)
                display_end_time = media.start_time + manim_duration

                # Ensure alpha channel exists for mp4
                media_v = media_v.filter("format", "yuva420p")
                media_v = media_v.filter("fps", fps=30)

                media_v = media_v.filter("scale", f"{self.manim_width}:-1")

                if self.manim_style and self.manim_style.corner_radius > 0:
                    media_v = Animator.rounded_corners(
                        media_v, self.manim_style.corner_radius
                    )
                media_v = media_v.filter(
                    "setpts", f"PTS-STARTPTS+{media.start_time}/TB"
                )
                is_static = False
            else:
                # Images/Latex are static
                is_static = True

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                is_static=is_static,
                easing="ease_in_out_quart",
            )

            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
                easing="ease_in_out_quart",
            )

            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{display_end_time})':eof_action=pass",
            )

        # 5. Subtitles
        main_v = main_v.filter("ass", f"'{subs_path}'")

        # Force final duration to match script
        main_v = main_v.filter("trim", duration=current_time)

        # 6. Audio Mixing
        final_audio = lip_concat_a
        if self.music:
            _, music_a = graph.add_input(self.music, "music")
            music_a = (
                music_a.filter("atrim", end=current_time)
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
        AssetType.MANIM,
        AssetType.LATEX,
        #AssetType.QUESTION,
    ]

    allowed_blocks = [BlockType.DIALOGUE, BlockType.QUESTION]

    def __init__(self, template_config: TemplateConfig):
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

        if block.type == "dialogue" and block.assets and block.assets.lipsync_filepath:
            seg_type = "video"
            video_path = block.assets.lipsync_filepath
        elif (
            block.type == "question" and block.assets and block.assets.question_filepath
        ):
            seg_type = "question"
            video_path = block.assets.question_filepath
            audio_path = block.assets.voice_filepath

        if seg_type != "none":
            duration = self.get_video_duration(video_path)
            return {
                "type": seg_type,
                "video": video_path,
                "audio": audio_path,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
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

        for i, seg in enumerate(segments):
            if seg["type"] == "video":
                v, a = graph.add_input(seg["video"], f"seg_{i}")
                v = v.filter("fps", fps=30)

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

                # Pad to Full Canvas (Avatar at Bottom)
                # x=0, y=1920-1080=840
                v = v.filter("pad", "1080:1920:0:840:color=0x00000000")

            elif seg["type"] == "question":
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                # Scale question to fit width (1000px)
                v = v.filter("scale", "1000:-1")
                v = v.filter(
                    "pad", "1080:1920:(ow-iw)/2:(oh-ih)/2-200:color=0x00000000"
                )

                # Generate silence of full video duration to ensure sync
                silence = graph.add_raw(
                    [],
                    f"anullsrc=channel_layout=stereo:sample_rate=44100:d={seg['duration']}",
                    f"silence_{i}",
                )

                if seg["audio"]:
                    _, a_in = graph.add_input(seg["audio"], f"seg_{i}_a")
                    # Mix voice with silence.
                    a = graph.add_raw(
                        [silence, a_in],
                        "amix=inputs=2:duration=first:dropout_transition=0:normalize=0",
                        f"seg_{i}_mix",
                    )
                else:
                    a = silence

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        # Concat lipsyncs
        lip_concat_v = graph.add_raw(
            lip_v_nodes, f"concat=n={len(lip_v_nodes)}:v=1:a=0", "lip_concat_v"
        )
        lip_concat_a = graph.add_raw(
            lip_a_nodes, f"concat=n={len(lip_a_nodes)}:v=0:a=1", "lip_concat_a"
        )

        # Normalize audio levels
        lip_concat_a = lip_concat_a.filter("loudnorm", I="-16", TP="-1.5", LRA="11")

        # 2. Process Background
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=current_time).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        # 3. Overlay Lipsync on Background
        # Since lip_concat_v is now full canvas (1080x1920) with transparency, we overlay at 0:0
        main_v = graph.add_raw(
            [bg_v, lip_concat_v], "overlay=0:0:shortest=1", "stacked"
        )

        # 4. Media Overlays
        for i, media in enumerate(media_timings):
            # temporary for testing
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")

            display_end_time = media.end_time

            if media.media_type == "manim":
                # Manim is a video, scale to fit width and shift time
                manim_duration = self.get_video_duration(media.filepath)
                display_end_time = media.start_time + manim_duration

                # Ensure alpha channel exists for mp4
                media_v = media_v.filter("format", "yuva420p")
                media_v = media_v.filter("fps", fps=30)

                media_v = media_v.filter("scale", f"{self.manim_width}:-1")

                if self.manim_style and self.manim_style.corner_radius > 0:
                    media_v = Animator.rounded_corners(
                        media_v, self.manim_style.corner_radius
                    )
                media_v = media_v.filter(
                    "setpts", f"PTS-STARTPTS+{media.start_time}/TB"
                )
                is_static = False
            else:
                # Images/Latex are static
                is_static = True

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                is_static=is_static,
            )

            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
            )

            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{display_end_time})':eof_action=pass",
            )

        # 5. Subtitles
        main_v = main_v.filter("ass", f"'{subs_path}'")

        # Force final duration to match script
        main_v = main_v.filter("trim", duration=current_time)

        # 6. Audio Mixing
        final_audio = lip_concat_a
        if self.music:
            _, music_a = graph.add_input(self.music, "music")
            music_a = (
                music_a.filter("atrim", end=current_time)
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


class StaticGameplayTemplate(EditTemplate):
    provider_name = "static_gameplay"

    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.STATICFACE,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.MANIM,
        AssetType.LATEX,
        #AssetType.QUESTION,
    ]

    allowed_blocks = [BlockType.DIALOGUE, BlockType.QUESTION]

    def __init__(self, template_config: TemplateConfig):
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

        if (
            block.type == "dialogue"
            and block.assets
            and block.assets.staticface_filepath
            and block.assets.voice_filepath
        ):
            seg_type = "static_face"
            video_path = block.assets.staticface_filepath
            audio_path = block.assets.voice_filepath
            duration = self.get_video_duration(
                audio_path
            )  # Duration based on audio for static face
        elif (
            block.type == "question" and block.assets and block.assets.question_filepath
        ):
            seg_type = "question"
            video_path = block.assets.question_filepath
            audio_path = block.assets.voice_filepath
            duration = self.get_video_duration(video_path)

        if seg_type != "none":
            return {
                "type": seg_type,
                "video": video_path,
                "audio": audio_path,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
        )

        # Generate subtitles file
        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        # --- Build Filter Graph ---
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

                # Scale and Pad (Avatar at Bottom)
                v = v.filter("scale", "1080:1080")
                v = v.filter("pad", "1080:1920:0:840:color=0x00000000")
                v = v.filter("format", "yuva420p")

            elif seg["type"] == "question":
                # Same logic as AlphaGameplayTemplate for questions
                v, _ = graph.add_input(seg["video"], f"seg_{i}_v")
                v = v.filter("scale", "1000:-1")
                v = v.filter(
                    "pad", "1080:1920:(ow-iw)/2:(oh-ih)/2-200:color=0x00000000"
                )

                silence = graph.add_raw(
                    [],
                    f"anullsrc=channel_layout=stereo:sample_rate=44100:d={seg['duration']}",
                    f"silence_{i}",
                )

                if seg["audio"]:
                    _, a_in = graph.add_input(seg["audio"], f"seg_{i}_a")
                    a = graph.add_raw(
                        [silence, a_in],
                        "amix=inputs=2:duration=first:dropout_transition=0:normalize=0",
                        f"seg_{i}_mix",
                    )
                else:
                    a = silence

            lip_v_nodes.append(v)
            lip_a_nodes.append(a)

        lip_concat_v = graph.add_raw(
            lip_v_nodes, f"concat=n={len(lip_v_nodes)}:v=1:a=0", "lip_concat_v"
        )
        lip_concat_a = graph.add_raw(
            lip_a_nodes, f"concat=n={len(lip_a_nodes)}:v=0:a=1", "lip_concat_a"
        )
        lip_concat_a = lip_concat_a.filter("loudnorm", I="-16", TP="-1.5", LRA="11")

        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=current_time).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        main_v = graph.add_raw(
            [bg_v, lip_concat_v], "overlay=0:0:shortest=1", "stacked"
        )

        # Media Overlays
        for i, media in enumerate(media_timings):
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")

            display_end_time = media.end_time

            if media.media_type == "manim":
                manim_duration = self.get_video_duration(media.filepath)
                display_end_time = media.start_time + manim_duration

                # Ensure alpha channel exists for mp4
                media_v = media_v.filter("format", "yuva420p")

                media_v = media_v.filter("scale", f"{self.manim_width}:-1")

                if self.manim_style and self.manim_style.corner_radius > 0:
                    media_v = Animator.rounded_corners(
                        media_v, self.manim_style.corner_radius
                    )
                media_v = media_v.filter("setpts", f"PTS+{media.start_time}/TB")
                is_static = False
            else:
                is_static = True

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                is_static=is_static,
            )
            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
            )

            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{display_end_time})':eof_action=pass",
            )

        main_v = main_v.filter("ass", f"'{subs_path}'")

        final_audio = lip_concat_a
        if self.music:
            _, music_a = graph.add_input(self.music, "music")
            music_a = (
                music_a.filter("atrim", end=current_time)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("volume", "0.2")
            )
            final_audio = graph.add_raw(
                [final_audio, music_a], "amix=inputs=2:normalize=0", "audio_mix"
            )

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=["-preset", "fast", "-c:a", "aac", "-r", "30"],
        )


class SongTemplate(EditTemplate):
    provider_name = "song"

    required_assets = [
        AssetType.SCRIPT,
        AssetType.SONG,
        AssetType.SUBTITLES,
        AssetType.IMAGES,
        AssetType.MANIM,
        AssetType.LATEX,
    ]

    allowed_blocks = [BlockType.SONG]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.subtitle_style = template_config.subtitle_style
        self.manim_width = template_config.manim_width
        self.manim_style = template_config.manim_style

    def _get_block_segment(self, block):
        if (
            AssetType.SONG in block.valid_assets
            and block.assets
            and block.assets.song_filepath
        ):
            duration = self.get_video_duration(block.assets.song_filepath)
            return {
                "type": "song",
                "audio": block.assets.song_filepath,
                "duration": duration,
            }
        return None

    def compose(self, reel: Reel) -> FFmpegCommand:
        segments, final_subtitles, media_timings, current_time = (
            self.collect_segments_and_timings(reel)
        )

        if current_time <= 0:
            raise ValueError(
                "Video duration is 0. Ensure the script contains valid Song blocks and song generation succeeded."
            )

        # Generate subtitles file
        subs_path = self.transcription_to_ass(
            transcription=final_subtitles,
            style=self.subtitle_style,
        ).download()

        # --- Build Filter Graph ---
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

        # 2. Process Background
        bg_v, _ = graph.add_input(self.bg_video, "bg_video")
        bg_v = bg_v.filter("trim", end=current_time).filter("setpts", "PTS-STARTPTS")
        bg_v = bg_v.filter("scale", "1080:1920:force_original_aspect_ratio=increase")
        bg_v = bg_v.filter("crop", "1080:1920")

        main_v = bg_v

        # 3. Media Overlays
        for i, media in enumerate(media_timings):
            if not os.path.isfile(media.filepath):
                continue

            media_v, _ = graph.add_input(media.filepath, f"media_{i}")
            display_end_time = media.end_time

            if media.media_type == "manim":
                manim_duration = self.get_video_duration(media.filepath)
                display_end_time = media.start_time + manim_duration
                media_v = media_v.filter("format", "yuva420p")
                media_v = media_v.filter("fps", fps=30)
                media_v = media_v.filter("scale", f"{self.manim_width}:-1")
                if self.manim_style and self.manim_style.corner_radius > 0:
                    media_v = Animator.rounded_corners(
                        media_v, self.manim_style.corner_radius
                    )
                media_v = media_v.filter(
                    "setpts", f"PTS-STARTPTS+{media.start_time}/TB"
                )
                is_static = False
            else:
                is_static = True

            media_v = Animator.fade(
                media_v,
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                is_static=is_static,
                easing="ease_in_out_quart",
            )
            x_expr = Animator.slide_horizontal(
                start_time=media.start_time,
                end_time=display_end_time,
                duration=0.4,
                enter_from="left",
                exit_to="right",
                easing="ease_in_out_quart",
            )
            main_v = graph.add_raw(
                [main_v, media_v],
                f"overlay=x='{x_expr}':y=100:enable='between(t,{media.start_time},{display_end_time})':eof_action=pass",
            )

        # 4. Subtitles & Final Trim
        main_v = main_v.filter("ass", f"'{subs_path}'")
        main_v = main_v.filter("trim", duration=current_time)

        return graph.build(
            video_out=main_v,
            audio_out=final_audio,
            extra_args=["-preset", "fast", "-c:a", "aac", "-r", "30"],
        )
