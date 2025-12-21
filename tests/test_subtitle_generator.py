import pytest
from unittest.mock import MagicMock, patch
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.tts.tts_providers import TTSResult


@patch("aishorts.modules.subtitles.subtitle_generator.SubtitlesProvider.get")
def test_init(mock_get):
    mock_cls = MagicMock()
    mock_get.return_value = mock_cls

    gen = SubtitleGenerator(provider="whisper", api_key="key")

    mock_get.assert_called_once_with("whisper")
    mock_cls.assert_called_once_with(api_key="key")
    assert gen.subtitle == mock_cls.return_value


@patch("aishorts.modules.subtitles.subtitle_generator.SubtitlesProvider.get")
def test_init_unknown(mock_get):
    mock_get.return_value = None
    with pytest.raises(ValueError, match="Unknown Subtitle provider"):
        SubtitleGenerator(provider="unknown")


@pytest.mark.asyncio
@patch("aishorts.modules.subtitles.subtitle_generator.SubtitlesProvider.get")
@patch("aishorts.modules.subtitles.subtitle_generator.await_or_thread")
async def test_generate_subtitles(mock_await, mock_get):
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    # Mock await_or_thread behavior
    async def mock_runner(func, *args, **kwargs):
        return "subtitle_result"

    mock_await.side_effect = mock_runner

    gen = SubtitleGenerator()
    result = await gen.generate_subtitles("audio.wav", text="abc")

    assert result == "subtitle_result"
    mock_await.assert_called_once()
    # Check that the first arg to await_or_thread was the instance method
    assert mock_await.call_args[0][0] == mock_instance.generate_subtitles


@pytest.mark.asyncio
@patch("aishorts.modules.subtitles.subtitle_generator.SubtitlesProvider.get")
@patch("aishorts.modules.subtitles.subtitle_generator.await_or_thread")
async def test_generate_multiple_subtitles(mock_await, mock_get):
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    async def mock_runner(func, *args, **kwargs):
        return ["sub1", "sub2"]

    mock_await.side_effect = mock_runner

    gen = SubtitleGenerator()
    result = await gen.generate_multiple_subtitles([])

    assert result == ["sub1", "sub2"]
    mock_await.assert_called_once()
    assert mock_await.call_args[0][0] == mock_instance.generate_multiple_subtitles
