from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    LOCAL = "local"
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"


class ProviderStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class StorageMetrics(BaseModel):
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    usage_percent: float = 0.0


class ProviderScan(BaseModel):
    provider_id: str
    provider_type: ProviderType
    display_name: str
    account_email: str | None = None
    status: ProviderStatus
    scanned_at: datetime
    metrics: StorageMetrics | None = None
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class UnifiedStorageSummary(BaseModel):
    scanned_at: datetime
    providers: list[ProviderScan]
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    online_providers: int
    offline_providers: int
