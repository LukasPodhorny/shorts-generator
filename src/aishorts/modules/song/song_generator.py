from aishorts.modules.song.song_providers import SongProvider
from aishorts.modules.script.script import Reel
from aishorts.utils.async_utils import await_or_thread


class SongGenerator:
    """
    Parameters:
        provider: str
            The provider to use (e.g., 'minimax').
    """

    def __init__(self, provider: str = "minimax", **kwargs):
        self.provider_cls = SongProvider.get(provider)
        self.provider = self.provider_cls(**kwargs)

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates songs and populates the reel.blocks[i].assets fields in-place."""
        func = self.provider.populate_reel

        await await_or_thread(func, reel, **kwargs)

        return reel
