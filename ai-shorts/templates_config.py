from video_edit import VideoTemplate, TemplateConfig, SubtitleStyle

TEMPLATES = {
    "gameplay_0": VideoTemplate(
        edit_template="gameplay",
        template_config=TemplateConfig(
            bg_video="assets/bg_video/gameplay.mp4",
            music="assets/music/music.mp3",
            subtitle_style=SubtitleStyle(font="assets/fonts/NotoSans-Bold.ttf"),
        ),
    )
}
