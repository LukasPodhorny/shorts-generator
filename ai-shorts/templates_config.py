from video_edit import VideoTemplate, TemplateConfig, SubtitleStyle

TEMPLATES = {
    "gameplay_0": VideoTemplate(
        edit_template="gameplay",
        template_config=TemplateConfig(
            bg_video="input/example.mp4",
            music="input/example.mp3",
            subtitle_style=SubtitleStyle(font="assets/fonts/NotoSans-Bold.ttf"),
        ),
    )
}
