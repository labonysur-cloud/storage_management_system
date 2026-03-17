from abc import ABC, abstractmethod

from app.models.storage import ProviderScan


class StorageProvider(ABC):
    def __init__(self, provider_id: str, display_name: str, account_email: str | None = None) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.account_email = account_email

    @abstractmethod
    async def scan(self) -> ProviderScan:
        raise NotImplementedError
