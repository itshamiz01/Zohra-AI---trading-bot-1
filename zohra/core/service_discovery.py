"""
Static service topology and readiness checks for the V2 architecture.

Zohra is intentionally a fixed local topology in Y1: Core, Trading Execution,
Tool Sandbox, and Voice Pipeline. This module keeps that decision explicit and
detects degraded cross-process capabilities without adding service-mesh
complexity.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class ServiceConfig:
    service_id: str
    name: str
    host: str
    port: int
    health_path: str = "/healthz"
    required: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.base_url}{self.health_path}"


@dataclass
class ServiceHealth:
    service_id: str
    status: str
    url: str
    latency_ms: float
    error: Optional[str] = None
    checked_at: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "service_id": self.service_id,
            "status": self.status,
            "url": self.url,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "checked_at": self.checked_at,
        }


def _parse_scalar(value: str):
    value = value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def load_services(path: Optional[str] = None) -> Dict[str, ServiceConfig]:
    path = path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "services.yaml",
    )
    services: Dict[str, Dict] = {}
    current_id: Optional[str] = None

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current_id = line[:-1].strip()
                services[current_id] = {}
                continue
            if current_id and ":" in line:
                key, value = line.strip().split(":", 1)
                services[current_id][key.strip()] = _parse_scalar(value)

    return {
        service_id: ServiceConfig(
            service_id=service_id,
            name=str(data.get("name", service_id)),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 0)),
            health_path=str(data.get("health_path", "/healthz")),
            required=bool(data.get("required", True)),
        )
        for service_id, data in services.items()
    }


class StaticServiceRegistry:
    def __init__(self, services: Optional[Dict[str, ServiceConfig]] = None):
        self.services = services or load_services()
        self._miss_counts: Dict[str, int] = {service_id: 0 for service_id in self.services}

    def get(self, service_id: str) -> ServiceConfig:
        return self.services[service_id]

    def list(self) -> Iterable[ServiceConfig]:
        return self.services.values()

    def check_service(self, service: ServiceConfig, timeout_sec: float = 0.5) -> ServiceHealth:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(service.health_url, timeout=timeout_sec) as response:
                status = "healthy" if 200 <= response.status < 300 else "degraded"
                error = None if status == "healthy" else f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status = "unreachable"
            error = str(exc)

        latency_ms = (time.perf_counter() - started) * 1000
        if status == "healthy":
            self._miss_counts[service.service_id] = 0
        else:
            self._miss_counts[service.service_id] = self._miss_counts.get(service.service_id, 0) + 1
            if self._miss_counts[service.service_id] >= 3:
                status = "degraded"

        return ServiceHealth(
            service_id=service.service_id,
            status=status,
            url=service.health_url,
            latency_ms=latency_ms,
            error=error,
            checked_at=time.time(),
        )

    def readiness(self, timeout_sec: float = 0.5, skip_core: bool = True) -> Dict:
        checks = []
        degraded_required = []

        for service in self.list():
            if skip_core and service.service_id == "core":
                checks.append({
                    "service_id": service.service_id,
                    "status": "healthy",
                    "url": service.health_url,
                    "latency_ms": 0.0,
                    "error": None,
                    "checked_at": time.time(),
                })
                continue

            health = self.check_service(service, timeout_sec=timeout_sec).to_dict()
            checks.append(health)
            if service.required and health["status"] != "healthy":
                degraded_required.append(service.service_id)

        return {
            "status": "degraded" if degraded_required else "ready",
            "degraded_required_services": degraded_required,
            "services": checks,
        }


service_registry = StaticServiceRegistry()
