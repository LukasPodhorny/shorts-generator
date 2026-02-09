from aishorts.modules.manim.manim_providers import ManimProvider, ManimResult
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.utils.async_utils import await_or_thread
import re


class ManimGenerator:
    def __init__(self, provider: str = "local", llm_provider: str = "gemini", **kwargs):
        self.provider_name = provider
        self.llm_provider = llm_provider

        cls = ManimProvider.get(self.provider_name)
        if not cls:
            raise ValueError(f"Unknown Manim provider '{provider}'")

        self.manim_provider = cls(**kwargs)
        self.script_gen = ScriptGenerator(provider=llm_provider)

    def _extract_code(self, text: str) -> str:
        # Try to find python code block
        match = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Try generic code block
        match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Assume the whole text is code if no blocks found
        return text

    async def generate(self, prompt: str, **kwargs) -> ManimResult:
        instructions = (
            "You are an expert in Manim (Community Edition). "
            "Write a Python script to visualize the user's request. "
            "Requirements:\n"
            "1. Import manim: `from manim import *`\n"
            "2. Create a Scene class named `GenScene`.\n"
            "3. The code must be complete and runnable.\n"
            "4. Do not use external assets (images/sounds) unless generated in code.\n"
            "5. Output ONLY the python code wrapped in ```python ... ``` blocks."
        )

        response = await self.script_gen.generate_response(
            instructions=instructions, user_input=prompt
        )

        code = self._extract_code(response)

        # If the LLM didn't use the required class name, we can try to patch it
        # or rely on the prompt instructions. For now, we rely on the prompt.
        if "class GenScene" not in code:
            # Fallback: try to find any scene class and rename it, or just warn
            # For simplicity, we assume the LLM follows instructions.
            pass

        func = self.manim_provider.render
        return await await_or_thread(func, code, **kwargs)
