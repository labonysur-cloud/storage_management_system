from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

import psutil

from app.models.storage import ProviderScan, ProviderStatus, ProviderType, StorageMetrics
from app.providers.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        account_email: str | None = None,
        paths: list[str] | None = None,
        scan_all_partitions: bool = True,
    ) -> None:
        super().__init__(provider_id=provider_id, display_name=display_name, account_email=account_email)
        self.paths = paths or []
        self.scan_all_partitions = scan_all_partitions

    async def scan(self) -> ProviderScan:
        scanned_at = datetime.now(timezone.utc)
        try:
            volumes = self._collect_volumes()
            if not volumes:
                raise RuntimeError("No local storage targets found. Check configured paths or disk visibility.")

            total_bytes = sum(volume["total_bytes"] for volume in volumes)
            used_bytes = sum(volume["used_bytes"] for volume in volumes)
            free_bytes = sum(volume["free_bytes"] for volume in volumes)
            usage_percent = (used_bytes / total_bytes * 100) if total_bytes else 0.0

            return ProviderScan(
                provider_id=self.provider_id,
                provider_type=ProviderType.LOCAL,
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
                raw={"volumes": volumes},
            )
        except Exception as exc:
            return ProviderScan(
                provider_id=self.provider_id,
                provider_type=ProviderType.LOCAL,
                display_name=self.display_name,
                account_email=self.account_email,
                status=ProviderStatus.OFFLINE,
                scanned_at=scanned_at,
                message=str(exc),
            )

    def _collect_volumes(self) -> list[dict[str, int | str]]:
        volumes: list[dict[str, int | str]] = []
        seen_targets: set[str] = set()

        if self.scan_all_partitions:
            for partition in psutil.disk_partitions(all=False):
                mountpoint = partition.mountpoint or partition.device
                if not mountpoint or mountpoint in seen_targets:
                    continue
                seen_targets.add(mountpoint)
                usage = shutil.disk_usage(mountpoint)
                volumes.append(
                    {
                        "target": mountpoint,
                        "source": partition.device or mountpoint,
                        "total_bytes": usage.total,
                        "used_bytes": usage.used,
                        "free_bytes": usage.free,
                    }
                )

        for path in self.paths:
            resolved_path = os.path.abspath(os.path.expanduser(path))
            if not os.path.exists(resolved_path):
                continue
            if resolved_path in seen_targets:
                continue
            seen_targets.add(resolved_path)
            usage = shutil.disk_usage(resolved_path)
            volumes.append(
                {
                    "target": resolved_path,
                    "source": resolved_path,
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                }
            )

        return volumes
