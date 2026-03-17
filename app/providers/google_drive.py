from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.models.storage import ProviderScan, ProviderStatus, ProviderType, StorageMetrics
from app.providers.base import StorageProvider


class GoogleDriveProvider(StorageProvider):
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        account_email: str | None,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_uri: str = "https://oauth2.googleapis.com/token",
        scopes: list[str] | None = None,
    ) -> None:
        super().__init__(provider_id=provider_id, display_name=display_name, account_email=account_email)
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.scopes = scopes or ["https://www.googleapis.com/auth/drive.metadata.readonly"]

    async def scan(self) -> ProviderScan:
        return await asyncio.to_thread(self._scan_sync)

    def _scan_sync(self) -> ProviderScan:
        scanned_at = datetime.now(timezone.utc)
        try:
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.scopes,
            )
            credentials.refresh(Request())

            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            about = service.about().get(fields="storageQuota,user").execute()
            quota = about.get("storageQuota", {})

            total_bytes = int(quota.get("limit", 0) or 0)
            used_bytes = int(quota.get("usage", 0) or 0)
            if total_bytes <= 0:
                total_bytes = used_bytes
            free_bytes = max(total_bytes - used_bytes, 0)
            usage_percent = (used_bytes / total_bytes * 100) if total_bytes else 0.0

            return ProviderScan(
                provider_id=self.provider_id,
                provider_type=ProviderType.GOOGLE_DRIVE,
                display_name=self.display_name,
                account_email=self.account_email or about.get("user", {}).get("emailAddress"),
                status=ProviderStatus.ONLINE,
                scanned_at=scanned_at,
                metrics=StorageMetrics(
                    total_bytes=total_bytes,
                    used_bytes=used_bytes,
                    free_bytes=free_bytes,
                    usage_percent=round(usage_percent, 2),
                ),
                raw={"storage_quota": quota, "user": about.get("user", {})},
            )
        except Exception as exc:
            return ProviderScan(
                provider_id=self.provider_id,
                provider_type=ProviderType.GOOGLE_DRIVE,
                display_name=self.display_name,
                account_email=self.account_email,
                status=ProviderStatus.OFFLINE,
                scanned_at=scanned_at,
                message=str(exc),
            )
