from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import zohra.config.settings as settings


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model_name: str
    reasoning_mode: str
    requires_network: bool
    fallback_provider: str
    reason: str


class ModelRouter:
    """Selects a model/provider using cost, risk, and offline availability."""

    def __init__(self, local_provider: str = "ollama"):
        self.local_provider = local_provider

    def _available_cloud_provider(self, provider: str) -> bool:
        provider = provider.lower()
        if provider == "openrouter":
            return bool(settings.OPENROUTER_API_KEY)
        if provider == "groq":
            return bool(settings.GROQ_API_KEY)
        return False

    def _provider_model(self, provider: str) -> str:
        provider = provider.lower()
        if provider == "openrouter":
            return getattr(settings, "OPENROUTER_MODEL", "openai/gpt-4o-mini")
        if provider == "groq":
            return getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        return getattr(settings, "OLLAMA_MODEL", "llama3.1:8b")

    def _preferred_cloud_provider(self) -> Optional[str]:
        configured = getattr(settings, "CHAT_PROVIDER", "openrouter").lower()
        candidates = [configured, "openrouter", "groq"]
        seen = set()
        for provider in candidates:
            provider = provider.lower()
            if provider in seen:
                continue
            seen.add(provider)
            if self._available_cloud_provider(provider):
                return provider
        return None

    def select_route(
        self,
        *,
        task_kind: str = "general",
        domain_risk: str = "normal",
        network_available: Optional[bool] = None,
        complexity: str = "medium",
        budget_remaining_usd: Optional[float] = None,
    ) -> ModelRoute:
        network_available = settings.NETWORK_AVAILABLE if network_available is None else network_available
        task_kind = (task_kind or "general").lower()
        domain_risk = (domain_risk or "normal").lower()
        complexity = (complexity or "medium").lower()

        if not network_available:
            return ModelRoute(
                provider=self.local_provider,
                model_name=self._provider_model(self.local_provider),
                reasoning_mode="local-offline",
                requires_network=False,
                fallback_provider=self.local_provider,
                reason="Network unavailable; forcing local fallback.",
            )

        cloud_provider = self._preferred_cloud_provider()
        if cloud_provider is None:
            return ModelRoute(
                provider=self.local_provider,
                model_name=self._provider_model(self.local_provider),
                reasoning_mode="local-fallback",
                requires_network=False,
                fallback_provider=self.local_provider,
                reason="No cloud provider is configured; forcing local fallback.",
            )

        if budget_remaining_usd is not None and budget_remaining_usd <= 0:
            return ModelRoute(
                provider=self.local_provider,
                model_name=self._provider_model(self.local_provider),
                reasoning_mode="budget-protected-local",
                requires_network=False,
                fallback_provider=self.local_provider,
                reason="Cloud budget exhausted; using local model.",
            )

        if domain_risk in {"high", "critical"} or task_kind in {"trading", "security", "file_delete"}:
            return ModelRoute(
                provider=cloud_provider,
                model_name=self._provider_model(cloud_provider),
                reasoning_mode="high-risk-cloud",
                requires_network=True,
                fallback_provider=self.local_provider,
                reason="High-consequence task routed to cloud reasoning.",
            )

        if budget_remaining_usd is not None and budget_remaining_usd < 5 and complexity in {"simple", "low"}:
            cheaper = "groq" if self._available_cloud_provider("groq") else cloud_provider
            return ModelRoute(
                provider=cheaper,
                model_name=self._provider_model(cheaper),
                reasoning_mode="cost-aware-cloud",
                requires_network=True,
                fallback_provider=self.local_provider,
                reason="Low-complexity task routed to the cheaper available cloud model.",
            )

        return ModelRoute(
            provider=cloud_provider,
            model_name=self._provider_model(cloud_provider),
            reasoning_mode="standard-cloud",
            requires_network=True,
            fallback_provider=self.local_provider,
            reason="Configured cloud provider selected.",
        )


model_router = ModelRouter()

