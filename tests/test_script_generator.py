import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aishorts.modules.script.script_generator import ScriptGenerator


# Mock Avatar class since we just need the attributes
class MockAvatar:
    def __init__(self, name, instructions):
        self.name = name
        self.instructions = instructions


@pytest.fixture
def mock_avatar():
    return MockAvatar(name="TestAvatar", instructions="Be funny")


@pytest.fixture
def script_generator(mock_avatar):
    with patch("aishorts.modules.script.script_generator.LLMProvider") as MockProvider:
        # Setup the mock returned by get()
        mock_llm_instance = MagicMock()
        mock_llm_cls = MagicMock(return_value=mock_llm_instance)
        MockProvider.get.return_value = mock_llm_cls

        generator = ScriptGenerator(
            base_instructions="Base rules.",
            avatars=[mock_avatar],
            generate_latex=True,
            generate_image=False,
            provider="chatgpt",
        )
        yield generator


def test_init_unknown_provider(mock_avatar):
    with patch("aishorts.modules.script.script_generator.LLMProvider") as MockProvider:
        MockProvider.get.return_value = None
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            ScriptGenerator("base", [mock_avatar], provider="unknown")


def test_generate_instructions(script_generator):
    instr = script_generator._generate_instructions(num_reels=3)

    assert "Base rules." in instr
    assert "Avatar 'TestAvatar': Be funny" in instr
    assert "Images: DISABLED" in instr
    assert "LaTeX: ENABLED" in instr
    assert "Number of reels to generate: 3" in instr


@pytest.mark.asyncio
async def test_generate_script_flow(script_generator):
    # Mock await_or_thread to just return the result of the func
    async def mock_runner(func, *args, **kwargs):
        return await func(*args, **kwargs)

    script_generator.llm.generate_script = AsyncMock(return_value="Success")

    with patch(
        "aishorts.modules.script.script_generator.await_or_thread",
        side_effect=mock_runner,
    ):
        result = await script_generator.generate_script(num_reels=1, user_input="test")

    assert result == "Success"
    script_generator.llm.generate_script.assert_called_once()
