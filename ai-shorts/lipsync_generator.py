from avatar import Avatar
from avatars_config import AVATARS
from lipsync_providers import FLOATLipsync, Wav2LipLipsync
from registry import LIPSYNC_PROVIDERS


class BaseLipsync:
    def generate_lipsync(self, audio_url: str) -> str:
        raise NotImplementedError("Subclasses must implement generate_lipsync()")


class LipsyncGenerator:
    """
    Parameters:
        avatar: Avatar
            The avatar whose voice configuration will be used.
        timeout: int, optional
            Used by FLOAT, Wav2lip backend only.
        endpoint_id: str, optional
            Used by FLOAT, Wav2lip backend only.
        api_key: str, optional
            Used by FLOAT, Wav2lip backend only.
    """

    def __init__(self, avatar: Avatar, **kwargs):
        self.avatar = avatar
        provider = self.avatar.lipsync_provider.lower()

        cls = LIPSYNC_PROVIDERS.get(provider)
        if not cls:
            raise ValueError(f"Unknown Lipsync provider '{provider}'")

        self.tts = cls(avatar=self.avatar, **kwargs)

    def generate_lipsync(self, audio_url: str, **kwargs) -> str:
        """
        Parameters:
            audio_url: str
                Link with audio file
            emotion: str
                Used by FLOAT backend only.
            seed: int
                Used by FLOAT backend only.
            a_cfg_scale: int
                Used by FLOAT backend only.
            e_cfg_scale: int
                Used by FLOAT backend only.
        """
        return self.tts.generate_lipsync(audio_url=audio_url, **kwargs)


if __name__ == "__main__":
    # long audio sample: https://files.catbox.moe/wbgzc8.wav
    result = LipsyncGenerator(AVATARS["biden"]).generate_lipsync(
        "https://files.catbox.moe/r234pd.wav"
    )
    print(result)
