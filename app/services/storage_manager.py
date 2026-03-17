from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings
from app.models.storage import ProviderScan, ProviderStatus, UnifiedStorageSummary
from app.providers.google_drive import GoogleDriveProvider
from app.providers.local import LocalStorageProvider
from app.providers.onedrive import OneDriveProvider
from app.providers.base import StorageProvider


class StorageManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._providers: list[StorageProvider] = []
        self._last_summary: UnifiedStorageSummary | None = None
        self._last_scan_at: datetime | None = None
        self._lock = asyncio.Lock()
        self.reload_provider_configs()

    def reload_provider_configs(self) -> None:
        config = self._load_config(self.settings.accounts_file)
        self._providers = self._build_providers(config)

    def list_provider_names(self) -> list[str]:
        return [provider.display_name for provider in self._providers]

    def get_settings_overview(self) -> dict[str, Any]:
        raw_config = self._load_raw_config(self.settings.accounts_file)
        provider_sections = {
            "local_storage": raw_config.get("local_storage", []),
            "google_drive": raw_config.get("google_drive", []),
            "onedrive": raw_config.get("onedrive", []),
        }

        providers: list[dict[str, Any]] = []
        env_checks: dict[str, bool] = {}
        inline_secret_count = 0

        for provider_type, entries in provider_sections.items():
            for entry in entries:
                provider_id = str(entry.get("id", "unlabeled-provider"))
                display_name = str(entry.get("display_name", provider_id))
                account_email = entry.get("account_email")
                checks, has_inline_secret = self._provider_secret_checks(provider_type, entry)
                inline_secret_count += int(has_inline_secret)

                for check in checks:
                    env_var = check.get("env_var")
                    if env_var:
                        env_checks[str(env_var)] = bool(check.get("configured"))

                providers.append(
                    {
                        "provider_id": provider_id,
                        "provider_type": provider_type,
                        "display_name": display_name,
                        "account_email": account_email,
                        "secret_checks": checks,
                        "is_ready": all(check.get("configured", False) for check in checks),
                        "has_inline_secret": has_inline_secret,
                    }
                )

        anthropic_ready = bool(self.settings.anthropic_api_key)
        env_checks["ANTHROPIC_API_KEY"] = anthropic_ready

        return {
            "accounts_file": str(self.settings.accounts_file),
            "providers": providers,
            "summary": {
                "provider_count": len(providers),
                "ready_providers": sum(1 for provider in providers if provider["is_ready"]),
                "providers_with_inline_secrets": inline_secret_count,
                "tracked_secret_variables": len(env_checks),
                "configured_secret_variables": sum(1 for value in env_checks.values() if value),
                "anthropic_ready": anthropic_ready,
            },
            "secret_variables": [
                {"name": name, "configured": configured} for name, configured in sorted(env_checks.items())
            ],
        }

    async def get_summary(self, force_refresh: bool = False) -> UnifiedStorageSummary:
        if not force_refresh and self._last_summary and self._last_scan_at and not self._cache_expired():
            return self._last_summary

        async with self._lock:
            if not force_refresh and self._last_summary and self._last_scan_at and not self._cache_expired():
                return self._last_summary

            provider_results = await asyncio.gather(*(provider.scan() for provider in self._providers))
            summary = self._aggregate(provider_results)
            self._last_summary = summary
            self._last_scan_at = summary.scanned_at
            return summary

    def _cache_expired(self) -> bool:
        if not self._last_scan_at:
            return True
        expires_at = self._last_scan_at + timedelta(seconds=self.settings.scan_cache_ttl_seconds)
        return datetime.now(timezone.utc) >= expires_at

    def _aggregate(self, provider_results: list[ProviderScan]) -> UnifiedStorageSummary:
        total_bytes = 0
        used_bytes = 0
        free_bytes = 0
        online_providers = 0

        for result in provider_results:
            if result.status != ProviderStatus.ONLINE or not result.metrics:
                continue
            online_providers += 1
            total_bytes += result.metrics.total_bytes
            used_bytes += result.metrics.used_bytes
            free_bytes += result.metrics.free_bytes

        usage_percent = (used_bytes / total_bytes * 100) if total_bytes else 0.0
        scanned_at = datetime.now(timezone.utc)

        return UnifiedStorageSummary(
            scanned_at=scanned_at,
            providers=provider_results,
            total_bytes=total_bytes,
            used_bytes=used_bytes,
            free_bytes=free_bytes,
            usage_percent=round(usage_percent, 2),
            online_providers=online_providers,
            offline_providers=len(provider_results) - online_providers,
        )

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as config_file:
            loaded_config = yaml.safe_load(config_file) or {}
        return self._resolve_env_values(loaded_config)

    def _load_raw_config(self, config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}

    def _resolve_env_values(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve_env_values(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_env_values(item) for item in value]
        if isinstance(value, str):
            return self._resolve_env_string(value)
        return value

    def _resolve_env_string(self, value: str) -> str:
        pattern = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")

        def replace(match: re.Match[str]) -> str:
            env_name = match.group(1)
            default_value = match.group(2)
            if env_name in os.environ:
                return os.environ[env_name]
            if default_value is not None:
                return default_value
            raise RuntimeError(
                f"Missing environment variable '{env_name}' referenced from accounts config."
            )

        return pattern.sub(replace, value)

    def _provider_secret_checks(self, provider_type: str, provider_entry: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        fields_by_provider = {
            "google_drive": ["client_id", "client_secret", "refresh_token"],
            "onedrive": ["client_id", "client_secret", "refresh_token", "access_token"],
            "local_storage": [],
        }
        secret_fields = fields_by_provider.get(provider_type, [])
        checks: list[dict[str, Any]] = []
        has_inline_secret = False

        placeholder_pattern = re.compile(r"^\$\{([A-Z0-9_]+)(?::-(.*?))?\}$")

        for field_name in secret_fields:
            raw_value = provider_entry.get(field_name)
            if raw_value is None or raw_value == "":
                checks.append(
                    {
                        "field": field_name,
                        "source": "missing",
                        "configured": False,
                    }
                )
                continue

            if isinstance(raw_value, str):
                match = placeholder_pattern.match(raw_value.strip())
                if match:
                    env_var = match.group(1)
                    default_value = match.group(2)
                    configured = env_var in os.environ or (default_value is not None and default_value != "")
                    checks.append(
                        {
                            "field": field_name,
                            "source": "env",
                            "env_var": env_var,
                            "configured": configured,
                        }
                    )
                    continue

                has_inline_secret = True
                checks.append(
                    {
                        "field": field_name,
                        "source": "inline",
                        "configured": True,
                    }
                )
                continue

            checks.append(
                {
                    "field": field_name,
                    "source": "non-string",
                    "configured": bool(raw_value),
                }
            )

        return checks, has_inline_secret

    def _build_providers(self, config: dict[str, Any]) -> list[StorageProvider]:
        providers: list[StorageProvider] = []

        for local_config in config.get("local_storage", []) or [{"id": "local-default", "display_name": "Local Storage", "scan_all_partitions": True}]:
            providers.append(
                LocalStorageProvider(
                    provider_id=local_config["id"],
                    display_name=local_config.get("display_name", local_config["id"]),
                    account_email=local_config.get("account_email"),
                    paths=local_config.get("paths", []),
                    scan_all_partitions=local_config.get("scan_all_partitions", True),
                )
            )

        for google_config in config.get("google_drive", []):
            providers.append(
                GoogleDriveProvider(
                    provider_id=google_config["id"],
                    display_name=google_config.get("display_name", google_config["id"]),
                    account_email=google_config.get("account_email"),
                    client_id=google_config["client_id"],
                    client_secret=google_config["client_secret"],
                    refresh_token=google_config["refresh_token"],
                    token_uri=google_config.get("token_uri", "https://oauth2.googleapis.com/token"),
                    scopes=google_config.get("scopes"),
                )
            )

        for onedrive_config in config.get("onedrive", []):
            providers.append(
                OneDriveProvider(
                    provider_id=onedrive_config["id"],
                    display_name=onedrive_config.get("display_name", onedrive_config["id"]),
                    account_email=onedrive_config.get("account_email"),
                    access_token=onedrive_config.get("access_token"),
                    refresh_token=onedrive_config.get("refresh_token"),
                    client_id=onedrive_config.get("client_id"),
                    client_secret=onedrive_config.get("client_secret"),
                    tenant_id=onedrive_config.get("tenant_id", "consumers"),
                    scopes=onedrive_config.get("scopes"),
                )
            )

        return providers
