from aishorts.modules.question.question_providers import QuestionProvider
from aishorts.modules.script.script import Reel
from aishorts.utils.async_utils import await_or_thread


class QuestionGenerator:
    def __init__(self, provider: str = "motion_graphic", **kwargs):
        self.provider = provider.lower()

        cls = QuestionProvider.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown Question provider '{provider}'")

        self.question_gen = cls(**kwargs)

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        func = self.question_gen.populate_reel
        await await_or_thread(func, reel, **kwargs)
        return reel
