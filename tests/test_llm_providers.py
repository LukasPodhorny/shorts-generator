import pytest
from unittest.mock import MagicMock, AsyncMock
from aishorts.modules.script.llm_providers import ChatGPT


@pytest.fixture
def chatgpt_provider():
    return ChatGPT(api_key="fake-key")


def test_chatgpt_init():
    provider = ChatGPT(api_key="test", model="gpt-4o")
    assert provider.model == "gpt-4o"
    assert provider.client is not None


def test_build_messages_text_only(chatgpt_provider):
    msgs = chatgpt_provider._build_messages("system instr", "user input", [])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "developer"
    assert msgs[0]["content"] == "system instr"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "user input"


def test_build_messages_with_files(chatgpt_provider):
    mock_file = MagicMock()
    mock_file.id = "file-123"

    msgs = chatgpt_provider._build_messages("instr", "user input", [mock_file])

    assert len(msgs) == 2
    content = msgs[1]["content"]
    assert isinstance(content, list)
    # Check file part
    assert content[0]["type"] == "input_file"
    assert content[0]["file_id"] == "file-123"
    # Check text part
    assert content[1]["type"] == "input_text"
    assert content[1]["text"] == "user input"


@pytest.mark.asyncio
async def test_generate_script_no_input(chatgpt_provider):
    with pytest.raises(
        ValueError, match="Either 'files' or 'user_input' must be provided"
    ):
        await chatgpt_provider.generate_script("instr")


@pytest.mark.asyncio
async def test_generate_script_success(chatgpt_provider):
    # Mock the client response
    mock_response = MagicMock()
    mock_response.output_parsed = "parsed_result"

    chatgpt_provider.client.responses = MagicMock()
    chatgpt_provider.client.responses.parse = AsyncMock(return_value=mock_response)

    result = await chatgpt_provider.generate_script(
        instructions="instr", user_input="hello"
    )

    assert result == "parsed_result"
    chatgpt_provider.client.responses.parse.assert_called_once()
