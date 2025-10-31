from openai.types.audio import TranscriptionVerbose, TranscriptionWord

TEST_SUBTITLES = TranscriptionVerbose(
    duration=10.0,
    language="english",
    text="You get to face a lot of s**t, young man. You got a long journey ahead of you because you're going to find out that while your dad did a lot of s**t to you, you're going to have to make it on your own.",
    segments=None,
    usage={"seconds": 10.0, "type": "duration"},
    words=[
        TranscriptionWord(end=0.3799999952316284, start=0.0, word="You"),
        TranscriptionWord(end=0.5, start=0.3799999952316284, word="get"),
        TranscriptionWord(end=0.6600000262260437, start=0.5, word="to"),
        TranscriptionWord(
            end=0.8999999761581421, start=0.6600000262260437, word="face"
        ),
        TranscriptionWord(end=1.1799999475479126, start=0.8999999761581421, word="a"),
        TranscriptionWord(end=1.2599999904632568, start=1.1799999475479126, word="lot"),
        TranscriptionWord(end=1.7400000095367432, start=1.2599999904632568, word="of"),
        TranscriptionWord(
            end=1.7400000095367432, start=1.7400000095367432, word="s**t"
        ),
        TranscriptionWord(
            end=1.8799999952316284, start=1.7400000095367432, word="young"
        ),
        TranscriptionWord(end=2.240000009536743, start=1.8799999952316284, word="man"),
        TranscriptionWord(end=2.799999952316284, start=2.7200000286102295, word="You"),
        TranscriptionWord(end=2.9200000762939453, start=2.799999952316284, word="got"),
        TranscriptionWord(end=3.0999999046325684, start=2.9200000762939453, word="a"),
        TranscriptionWord(end=3.5, start=3.0999999046325684, word="long"),
        TranscriptionWord(end=3.759999990463257, start=3.5, word="journey"),
        TranscriptionWord(end=4.0, start=3.759999990463257, word="ahead"),
        TranscriptionWord(end=4.139999866485596, start=4.0, word="of"),
        TranscriptionWord(end=4.21999979019165, start=4.139999866485596, word="you"),
        TranscriptionWord(
            end=4.380000114440918, start=4.21999979019165, word="because"
        ),
        TranscriptionWord(
            end=4.599999904632568, start=4.380000114440918, word="you're"
        ),
        TranscriptionWord(end=4.599999904632568, start=4.599999904632568, word="going"),
        TranscriptionWord(end=4.940000057220459, start=4.599999904632568, word="to"),
        TranscriptionWord(end=4.960000038146973, start=4.940000057220459, word="find"),
        TranscriptionWord(end=5.400000095367432, start=4.960000038146973, word="out"),
        TranscriptionWord(end=5.900000095367432, start=5.539999961853027, word="that"),
        TranscriptionWord(end=6.119999885559082, start=5.900000095367432, word="while"),
        TranscriptionWord(end=6.460000038146973, start=6.119999885559082, word="your"),
        TranscriptionWord(end=6.519999980926514, start=6.460000038146973, word="dad"),
        TranscriptionWord(end=6.739999771118164, start=6.519999980926514, word="did"),
        TranscriptionWord(end=6.860000133514404, start=6.739999771118164, word="a"),
        TranscriptionWord(end=6.860000133514404, start=6.860000133514404, word="lot"),
        TranscriptionWord(end=7.019999980926514, start=6.860000133514404, word="of"),
        TranscriptionWord(end=7.099999904632568, start=7.019999980926514, word="s**t"),
        TranscriptionWord(end=7.380000114440918, start=7.099999904632568, word="to"),
        TranscriptionWord(end=7.639999866485596, start=7.380000114440918, word="you"),
        TranscriptionWord(end=8.739999771118164, start=8.4399995803833, word="you're"),
        TranscriptionWord(end=8.739999771118164, start=8.739999771118164, word="going"),
        TranscriptionWord(end=8.880000114440918, start=8.739999771118164, word="to"),
        TranscriptionWord(end=9.0600004196167, start=8.880000114440918, word="have"),
        TranscriptionWord(end=9.180000305175781, start=9.0600004196167, word="to"),
        TranscriptionWord(end=9.34000015258789, start=9.180000305175781, word="make"),
        TranscriptionWord(end=9.4399995803833, start=9.34000015258789, word="it"),
        TranscriptionWord(end=9.579999923706055, start=9.4399995803833, word="on"),
        TranscriptionWord(end=9.720000267028809, start=9.579999923706055, word="your"),
        TranscriptionWord(end=9.899999618530273, start=9.720000267028809, word="own"),
    ],
    task="transcribe",
)
