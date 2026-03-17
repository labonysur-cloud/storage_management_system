from __future__ import annotations

import json

import httpx

from app.core.config import Settings
from app.models.storage import UnifiedStorageSummary


class AnthropicService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate_storage_insights(self, summary: UnifiedStorageSummary) -> str:
        if not self.settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

        prompt = self._build_prompt(summary)
        payload = {
            "model": self.settings.anthropic_model,
            "max_tokens": 800,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("content", [])
        text_blocks = [block.get("text", "") for block in content if block.get("type") == "text"]
        return "\n".join(block for block in text_blocks if block).strip()

    def _build_prompt(self, summary: UnifiedStorageSummary) -> str:
        serialized_summary = json.dumps(summary.model_dump(mode="json"), indent=2)
        return (
            "You are a storage operations assistant. Review the unified storage snapshot and produce: "
            "1) the highest-risk storage bottlenecks, 2) balancing recommendations across accounts, "
            "3) cleanup priorities, and 4) practical automation ideas for this setup. "
            "Keep the answer concise and operational.\n\n"
            f"Unified storage snapshot:\n{serialized_summary}"
        )