from aishorts.utils.registry import register_edit_template
from aishorts.utils.r2_handler import CloudflareR2
from aishorts.modules.video_edit.asset_type import AssetType
from aishorts.modules.video_edit.video_edit import (
    EditTemplate,
    TemplateConfig,
    TemplateAssets,
)
import subprocess


@register_edit_template("gameplay_ffmpeg")
class GameplayTemplate(EditTemplate):
    required_assets = [
        AssetType.SCRIPT,
        AssetType.VOICE,
        AssetType.LIPSYNC,
        AssetType.SUBTITLES,
    ]

    def __init__(self, template_config: TemplateConfig):
        self.bg_video = template_config.bg_video
        self.music = template_config.music  # Can be None
        self.subtitle_style = template_config.subtitle_style

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def compose(self, template_assets: TemplateAssets):
        # ============================================================
        #  1. OUTPUT PATH
        # ============================================================
        output_path = CloudflareR2.get_random_filepath(EditTemplate.OUTPUT_DIR, ".mp4")

        # ============================================================
        #  2. GET LIPSYNC DURATION
        # ============================================================
        lipsync_duration = self.get_video_duration(template_assets.lipsync_video)

        # ============================================================
        #  3. Generate ASS subtitles for word-by-word display
        # ============================================================
        subs_ass = self.transcription_to_ass(
            transcription=template_assets.subtitles,
            style=self.subtitle_style,
        )
        subs_path = "/tmp/subs.ass"
        with open(subs_path, "w", encoding="utf-8") as f:
            f.write(subs_ass)

        # ============================================================
        #  4. FFmpeg Filter Graph - Conditional music handling
        # ============================================================
        if self.music is not None:
            # With music
            filter_graph = f"""
                [0:v] scale=1080:-1, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [lip];
                [1:v] trim=end={lipsync_duration}, setpts=PTS-STARTPTS, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [game];
                [lip][game] vstack=inputs=2 [stacked];
                [stacked] ass={subs_path} [video];
                [0:a] volume=5.0 [voice];
                [2:a] atrim=end={lipsync_duration}, asetpts=PTS-STARTPTS, volume=0.2 [music];
                [voice][music] amix=inputs=2:normalize=0 [audio]
            """
        else:
            # Without music - only voice audio
            filter_graph = f"""
                [0:v] scale=1080:-1, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [lip];
                [1:v] trim=end={lipsync_duration}, setpts=PTS-STARTPTS, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [game];
                [lip][game] vstack=inputs=2 [stacked];
                [stacked] ass={subs_path} [video];
                [0:a] volume=5.0 [audio]
            """

        # ============================================================
        #  5. Choose encoder: NVENC on GPU, libx264 on CPU
        # ============================================================
        video_codec = "h264_nvenc" if self.nvenc_available() else "libx264"

        # ============================================================
        #  6. Construct FFmpeg command - conditionally add music input
        # ============================================================
        cmd = [
            "ffmpeg",
            "-i",
            str(template_assets.lipsync_video),
            "-i",
            str(self.bg_video),
        ]

        # Add music input only if music is provided
        if self.music is not None:
            cmd.extend(["-i", str(self.music)])

        cmd.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[video]",
                "-map",
                "[audio]",
                "-c:v",
                video_codec,
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-r",
                "30",
                "-y",
                output_path,
            ]
        )

        # ============================================================
        #  7. Run FFmpeg
        # ============================================================
        subprocess.run(cmd, check=True)
        print(output_path)
        return output_path


'''
@register_edit_template("gameplay_ffmpeg")
class GameplayTemplate(EditTemplate):
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

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def compose(self, template_assets: TemplateAssets):
        # ============================================================
        #  1. OUTPUT PATH
        # ============================================================
        output_path = CloudflareR2.get_random_filepath(EditTemplate.OUTPUT_DIR, ".mp4")

        # ============================================================
        #  2. GET LIPSYNC DURATION
        # ============================================================
        lipsync_duration = self.get_video_duration(template_assets.lipsync_video)

        # ============================================================
        #  3. Generate ASS subtitles for word-by-word display
        # ============================================================
        subs_ass = self.transcription_to_ass(
            transcription=template_assets.subtitles,
            style=self.subtitle_style,
        )
        subs_path = "/tmp/subs.ass"
        with open(subs_path, "w", encoding="utf-8") as f:
            f.write(subs_ass)

        # ============================================================
        #  4. FFmpeg Filter Graph - Trim gameplay and music to lipsync duration
        # ============================================================
        filter_graph = f"""
            [0:v] scale=1080:-1, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [lip];
            [1:v] trim=end={lipsync_duration}, setpts=PTS-STARTPTS, crop=1080:960:(in_w-1080)/2:(in_h-960)/2 [game];
            [lip][game] vstack=inputs=2 [stacked];
            [stacked] ass={subs_path} [video];
            [0:a] volume=5.0 [voice];
            [2:a] atrim=end={lipsync_duration}, asetpts=PTS-STARTPTS, volume=0.2 [music];
            [voice][music] amix=inputs=2:normalize=0 [audio]
        """

        # ============================================================
        #  5. Choose encoder: NVENC on GPU, libx264 on CPU
        # ============================================================
        video_codec = "h264_nvenc" if self.nvenc_available() else "libx264"

        # ============================================================
        #  6. Construct FFmpeg command
        # ============================================================
        cmd = [
            "ffmpeg",
            "-i",
            str(template_assets.lipsync_video),
            "-i",
            str(self.bg_video),
            "-i",
            str(self.music),
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-c:v",
            video_codec,
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-r",
            "30",
            "-y",
            output_path,
        ]

        # ============================================================
        #  7. Run FFmpeg
        # ============================================================
        subprocess.run(cmd, check=True)
        print(output_path)
        return output_path
'''
