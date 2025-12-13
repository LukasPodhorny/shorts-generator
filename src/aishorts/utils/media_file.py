from pydantic import BaseModel
from aishorts.utils.r2_handler import CloudflareR2


class MediaFile(BaseModel):
    def __init__(self, url: str = None, path: str = None):
        self.url = url
        self.path = path