import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.image.image_providers import Unsplash, ImageResult
from aishorts.modules.script.script import Reel, Block, ImageMedia, Trigger
from aishorts.modules.provider import MediaFile


@pytest.fixture
def unsplash_provider():
    return Unsplash(api_key="test_key")


@pytest.mark.asyncio
async def test_search_query_success(unsplash_provider):
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "results": [
            {
                "urls": {"raw": "http://img.url"},
                "alt_description": "A nice photo",
            }
        ]
    }
    mock_session.get.return_value.__aenter__.return_value = mock_response

    result = await unsplash_provider._search_query(mock_session, "query", 100, 100)

    assert result is not None
    url, alt = result
    assert "http://img.url" in url
    assert "fm=png" in url
    assert alt == "A nice photo"


@pytest.mark.asyncio
async def test_search_query_no_results(unsplash_provider):
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {"results": []}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    result = await unsplash_provider._search_query(mock_session, "query", 100, 100)
    assert result is None


@pytest.mark.asyncio
@patch(
    "aishorts.modules.image.image_providers.download_from_url", new_callable=AsyncMock
)
async def test_get_images(mock_download, unsplash_provider):
    # Mock _search_query to avoid complex session mocking here
    unsplash_provider._search_query = AsyncMock(
        side_effect=[("http://url1", "alt1"), ("http://url2", "alt2")]
    )
    mock_download.side_effect = ["path1.png", "path2.png"]

    results = await unsplash_provider.get_images(["q1", "q2"], 100, 100)

    assert len(results) == 2
    assert results[0].media.path == "path1.png"
    assert results[0].alt == "alt1"
    assert results[1].media.path == "path2.png"


@pytest.mark.asyncio
async def test_get_reel_images(unsplash_provider):
    # Setup Reel
    trigger = Trigger(start_word_index=0, end_word_index=5)
    media = ImageMedia(type="image", keywords="cat", trigger=trigger)
    block1 = Block(type="dialogue", avatar="a", text="t", media=media)
    block2 = Block(type="dialogue", avatar="a", text="t", media=None)  # No media
    reel = Reel(title="T", description="D", blocks=[block1, block2])

    # Mock get_images to verify arguments passed from get_reel_images
    with patch.object(
        unsplash_provider, "get_images", new_callable=AsyncMock
    ) as mock_get_images:
        mock_get_images.return_value = [
            ImageResult(media=MediaFile(id=0, url="u", path="p"), alt="a")
        ]

        results = await unsplash_provider.get_reel_images(reel, 100, 100)

        assert len(results) == 1
        mock_get_images.assert_called_once()
        call_kwargs = mock_get_images.call_args.kwargs

        # Verify it extracted the correct keywords
        assert call_kwargs["queries"] == ["cat"]
        # Verify it mapped the index correctly (block 0 has the image)
        assert call_kwargs["ids"] == [0]
        assert call_kwargs["max_width"] == 100
        assert call_kwargs["max_height"] == 100
