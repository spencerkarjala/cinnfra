from abc import ABC, abstractmethod

from models import ArtworkResult


class BaseHandler(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        pass

    @abstractmethod
    async def fetch_artwork(self, url: str) -> list[ArtworkResult]:
        pass
