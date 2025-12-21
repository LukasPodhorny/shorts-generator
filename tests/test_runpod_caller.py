import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.utils.runpod_caller import EndpointCaller


@pytest.mark.asyncio
@patch("aishorts.utils.runpod_caller.runpod")
async def test_run_async_completed(mock_runpod):
    # Setup
    mock_endpoint = MagicMock()
    mock_runpod.Endpoint.return_value = mock_endpoint

    mock_run_req = MagicMock()
    mock_endpoint.run.return_value = mock_run_req

    # Status sequence: RUNNING -> COMPLETED
    mock_run_req.status.side_effect = ["RUNNING", "COMPLETED"]
    mock_run_req.output.return_value = {"result": "ok"}

    caller = EndpointCaller("ep_id", timeout=10, api_key="key")

    # Execute
    # We need to mock asyncio.sleep to avoid waiting real time
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await caller.run_async({"input": 1})

    assert result == {"result": "ok"}
    mock_endpoint.run.assert_called_with({"input": 1})


@pytest.mark.asyncio
@patch("aishorts.utils.runpod_caller.runpod")
async def test_run_async_failed(mock_runpod):
    mock_endpoint = MagicMock()
    mock_runpod.Endpoint.return_value = mock_endpoint
    mock_run_req = MagicMock()
    mock_endpoint.run.return_value = mock_run_req

    mock_run_req.status.return_value = "FAILED"

    caller = EndpointCaller("ep_id", timeout=10)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="RunPod job FAILED"):
            await caller.run_async({})


@pytest.mark.asyncio
@patch("aishorts.utils.runpod_caller.runpod")
async def test_run_async_timeout(mock_runpod):
    mock_endpoint = MagicMock()
    mock_runpod.Endpoint.return_value = mock_endpoint
    mock_run_req = MagicMock()
    mock_endpoint.run.return_value = mock_run_req

    mock_run_req.status.return_value = "RUNNING"

    caller = EndpointCaller("ep_id", timeout=0.1)  # Short timeout

    # Mock sleep to advance time virtually or just be called
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(TimeoutError):
            await caller.run_async({}, poll_interval=0.2)
