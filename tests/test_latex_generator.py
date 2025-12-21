import pytest
from unittest.mock import MagicMock, patch
from aishorts.modules.latex.latex_generator import LatexGenerator
from aishorts.modules.latex.latex_providers import LatexResult, Resolution
from aishorts.modules.provider import MediaFile


@patch("aishorts.modules.latex.latex_generator.LatexProvider.get")
def test_init(mock_get):
    mock_cls = MagicMock()
    mock_get.return_value = mock_cls

    gen = LatexGenerator(provider="matplotlib")

    mock_get.assert_called_once_with("matplotlib")
    mock_cls.assert_called_once()


@patch("aishorts.modules.latex.latex_generator.LatexProvider.get")
def test_init_unknown(mock_get):
    mock_get.return_value = None
    with pytest.raises(ValueError, match="Unknown LaTex provider"):
        LatexGenerator(provider="unknown")


@pytest.mark.asyncio
@patch("aishorts.modules.latex.latex_generator.LatexProvider.get")
@patch("aishorts.modules.latex.latex_generator.await_or_thread")
@patch("aishorts.modules.latex.latex_generator.asyncio.to_thread")
async def test_get_images(mock_to_thread, mock_await, mock_get):
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    res = LatexResult(media=MediaFile(id=1, path="p"), alt="a")

    async def mock_runner(func, *args, **kwargs):
        return [res]

    mock_await.side_effect = mock_runner

    gen = LatexGenerator()
    results = await gen.get_images(["code"])

    assert len(results) == 1
    assert results[0] == res
    mock_await.assert_called_once()
    mock_to_thread.assert_called_once()  # Styling


@pytest.mark.asyncio
@patch("aishorts.modules.latex.latex_generator.LatexProvider.get")
@patch("aishorts.modules.latex.latex_generator.await_or_thread")
@patch("aishorts.modules.latex.latex_generator.asyncio.to_thread")
async def test_get_reel_images(mock_to_thread, mock_await, mock_get):
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    res = LatexResult(media=MediaFile(id=1, path="p"), alt="a")

    async def mock_runner(func, *args, **kwargs):
        return [res]

    mock_await.side_effect = mock_runner

    gen = LatexGenerator()
    await gen.get_reel_images(MagicMock())

    mock_await.assert_called_once()
    mock_to_thread.assert_called_once()
