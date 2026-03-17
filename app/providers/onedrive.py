from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.models.storage import ProviderScan, ProviderStatus, ProviderType, StorageMetrics
from app.providers.base import StorageProvider


class OneDriveProvider(StorageProvider):
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        account_email: str | None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str = "consumers",
        scopes: list[str] | None = None,
    ) -> None:
        super().__init__(provider_id=provider_id, display_name=display_name, account_email=account_email)
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.scopes = scopes or ["Files.Read", "User.Read", "offline_access"]

    async def scan(self) -> ProviderScan:
        scanned_at = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                access_token = await self._get_access_token(client)
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me/drive?$select=id,name,quota,owner",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                payload = response.json()
                quota = payload.get("quota", {})
                total_bytes = int(quota.get("total", 0) or 0)
                used_bytes = int(quota.get("used", 0) or 0)
                free_bytes = int(quota.get("remaining", max(total_bytes - used_bytes, 0)) or 0)
                usage_percent = (used_bytes / total_bytes * 100) if total_bytes else 0.0

                return ProviderScan(
                    provider_id=self.provider_id,
                    provider_type=ProviderType.ONEDRIVE,
                    display_name=self.display_name,
                    account_email=self.account_email,
                    status=ProviderStatus.ONLINE,
                    scanned_at=scanned_at,
                    metrics=StorageMetrics(
                        total_bytes=total_bytes,
                        used_bytes=used_bytes,
                        free_bytes=free_bytes,
                        usage_percent=round(usage_percent, 2),
                    ),
                    raw={"quota": quota, "drive": payload},
                )
        except Exception as exc:
            return ProviderScan(
                provider_id=self.provider_id,
                provider_type=ProviderType.ONEDRIVE,
                display_name=self.display_name,
                account_email=self.account_email,
                status=ProviderStatus.OFFLINE,
                scanned_at=scanned_at,
                message=str(exc),
            )

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        if self.access_token:
            return self.access_token

        if not self.refresh_token or not self.client_id:
            raise RuntimeError("OneDrive requires an access token or a refresh token with client_id.")

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": " ".join(f"https://graph.microsoft.com/{scope}" if not scope.startswith("https://") else scope for scope in self.scopes),
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        response = await client.post(token_url, data=data)
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("Microsoft token refresh succeeded without returning an access token.")
        return access_token
