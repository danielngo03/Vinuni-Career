"""
Circuit breaker for LLM provider resilience.

States:
  CLOSED     — Normal operation. Requests pass through.
  OPEN       — Provider is down. Requests fail fast without calling provider.
  HALF_OPEN  — Testing recovery. Allow one probe request; success → CLOSED, failure → OPEN.

Configuration per provider:
  failure_threshold  — Number of consecutive failures before tripping to OPEN.
  recovery_timeout   — Seconds before attempting probe from OPEN → HALF_OPEN.
  success_threshold  — Consecutive successes needed in HALF_OPEN → CLOSED.
"""
from __future__ import annotations

import threading
import time
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single provider."""

    def __init__(
        self,
        *,
        provider_name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        success_threshold: int = 1,
    ) -> None:
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state_locked()

    def _get_state_locked(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._last_failure_time or 0)
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
        return self._state

    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN

    def __repr__(self) -> str:
        return f"CircuitBreaker({self.provider_name!r}, state={self._state})"


class CircuitBreakerRegistry:
    """Registry of circuit breakers — one per provider, singleton per process."""

    _instance: CircuitBreakerRegistry | None = None
    _breakers: dict[str, CircuitBreaker]

    def __new__(cls) -> CircuitBreakerRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers = {}
        return cls._instance

    def get(self, provider_name: str) -> CircuitBreaker:
        if provider_name not in self._breakers:
            self._breakers[provider_name] = CircuitBreaker(provider_name=provider_name)
        return self._breakers[provider_name]

    def reset(self, provider_name: str | None = None) -> None:
        """Reset breakers — used in tests."""
        if provider_name:
            self._breakers.pop(provider_name, None)
        else:
            self._breakers.clear()


# Module-level singleton
circuit_registry = CircuitBreakerRegistry()
