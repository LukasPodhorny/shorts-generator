import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.lipsync.lipsync_providers import FLOATLipsync, LipsyncResult
from aishorts.modules.tts.tts_providers import TTSResult


class MockAvatar:
    def __init__(self, name, face_url, a_cfg_scale=1.0, e_cfg_scale=1.0):
        self.name = name
        self.face_url = face_url
        self.a_cfg_scale = a_cfg_scale
        self.e_cfg_scale = e_cfg_scale


@pytest.fixture
def mock_avatar():
    return MockAvatar("TestAvatar", "http://face.url")


@pytest.fixture
def float_provider(mock_avatar):
    # Mock EndpointCaller init to avoid network/env checks
    with patch("aishorts.modules.lipsync.lipsync_providers.EndpointCaller.__init__"):
        provider = FLOATLipsync(
            avatars=[mock_avatar],
            lipsync_float_api_key="key",
            endpoint_id="test_id",
        )
        # Manually set attributes usually set by super().__init__
        provider.endpoint_id = "test_id"
        provider.run_async = AsyncMock()
        return provider


def test_prepare_single_input(float_provider):
    result = float_provider._prepare_single_input("http://audio.url", "happy", 42, 1)
    expected_input = {
        "input": {
            "avatars": {
                "TestAvatar": {
                    "avatar_image": "http://face.url",
                    "seed": 42,
                    "a_cfg_scale": 1.0,
                    "e_cfg_scale": 1.0,
                }
            },
            "dialogues": [
                {
                    "avatar": "TestAvatar",
                    "audio_url": "http://audio.url",
                    "emotion": "happy",
                    "id": 1,
                }
            ],
        }
    }
    assert result == expected_input


def test_prepare_list_input(float_provider, mock_avatar):
    tts_res = TTSResult(id=1, url="http://audio.url", avatar=mock_avatar)
    result = float_provider._prepare_list_input([tts_res], "happy", 42)

    assert "input" in result
    assert "avatars" in result["input"]
    assert "dialogues" in result["input"]
    assert result["input"]["dialogues"][0]["audio_url"] == "http://audio.url"


@pytest.mark.asyncio
@patch(
    "aishorts.modules.lipsync.lipsync_providers.download_from_url",
    new_callable=AsyncMock,
)
async def test_generate_lipsync(mock_download, float_provider):
    # Mock response from run_async
    float_provider.run_async.return_value = ["http://video.url"]
    mock_download.return_value = "/path/to/video.mp4"

    res = await float_provider.generate_lipsync("http://audio.url", id=1)

    assert isinstance(res, LipsyncResult)
    assert res.filepath == "/path/to/video.mp4"
    assert res.url == "http://video.url"
    assert res.id == 1
    mock_download.assert_called_once()


@pytest.mark.asyncio
@patch(
    "aishorts.modules.lipsync.lipsync_providers.download_from_url",
    new_callable=AsyncMock,
)
async def test_generate_lipsyncs(mock_download, float_provider, mock_avatar):
    # Mock response from run_async for list input
    float_provider.run_async.return_value = [{"video_url": "http://video.url", "id": 1}]
    mock_download.return_value = "/path/to/video.mp4"

    tts_res = TTSResult(id=1, url="http://audio.url", avatar=mock_avatar)
    res_list = await float_provider.generate_lipsyncs([tts_res])

    assert len(res_list) == 1
    assert res_list[0].filepath == "/path/to/video.mp4"
    assert res_list[0].avatar == mock_avatar
    assert res_list[0].id == 1
    mock_download.assert_called_once()
