import pytest
from unittest.mock import MagicMock, patch
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.modules.image.image_providers import ImageResult
from aishorts.modules.provider import MediaFile


@patch("aishorts.modules.image.image_generator.ImageProvider.get")
def test_init(mock_get):
    mock_cls = MagicMock()
    mock_get.return_value = mock_cls

    ImageGenerator(provider="unsplash", api_key="key", max_concurrent_downloads=3)

    mock_get.assert_called_once_with("unsplash")
    mock_cls.assert_called_once_with(3, "key")


@patch("aishorts.modules.image.image_generator.ImageProvider.get")
def test_init_unknown(mock_get):
    mock_get.return_value = None
    with pytest.raises(ValueError, match="Unknown Image provider"):
        ImageGenerator(provider="unknown")


@pytest.mark.asyncio
@patch("aishorts.modules.image.image_generator.ImageProvider.get")
@patch("aishorts.modules.image.image_generator.await_or_thread")
@patch("aishorts.modules.image.image_generator.asyncio.to_thread")
async def test_get_images(mock_to_thread, mock_await, mock_get):
    # Setup provider
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    # Setup results
    img_res = ImageResult(media=MediaFile(id=1, url="u", path="p"), alt="a")

    # Mock await_or_thread to return results
    async def mock_runner(func, *args, **kwargs):
        return [img_res]

    mock_await.side_effect = mock_runner

    gen = ImageGenerator()
    results = await gen.get_images(["query"])

    assert len(results) == 1
    assert results[0] == img_res
    mock_await.assert_called_once()
    mock_to_thread.assert_called_once()


@pytest.mark.asyncio
@patch("aishorts.modules.image.image_generator.ImageProvider.get")
@patch("aishorts.modules.image.image_generator.await_or_thread")
@patch("aishorts.modules.image.image_generator.asyncio.to_thread")
async def test_get_reel_images_styling(mock_to_thread, mock_await, mock_get):
    mock_instance = MagicMock()
    mock_get.return_value = MagicMock(return_value=mock_instance)

    img_res = ImageResult(
        media=MediaFile(id=1, url="u", path="path/to/img.png"), alt="a"
    )

    async def mock_runner(func, *args, **kwargs):
        return [img_res]

    mock_await.side_effect = mock_runner

    gen = ImageGenerator()
    await gen.get_reel_images(MagicMock())

    # Verify styling was called via to_thread
    mock_to_thread.assert_called()
    args = mock_to_thread.call_args[0]
    # args[0] is the function style_image, args[1] is src path
    assert args[1] == "path/to/img.png"
