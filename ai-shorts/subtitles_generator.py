from openai import OpenAI


def generate_subtitles(audio_file):
    client = OpenAI()
    with open(audio_file, "rb") as audio:
        transcription = client.audio.transcriptions.create(
            file=audio,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    return transcription


if __name__ == "__main__":
    subtitles = generate_subtitles("test_files/biden-voice-veryshort.mp3")
    print(subtitles)
