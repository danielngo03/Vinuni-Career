"""Circuit-breaker HALF_OPEN single-probe tests (AI_PRODUCT_SPEC §5.2).

The breaker must not stampede a suspect provider the instant its recovery
window elapses: it enters HALF_OPEN and admits exactly ONE trial call. A
successful probe closes it; a failed probe re-opens it for another cooldown.
``is_open()`` stays back-compatible (True only in the fully-OPEN state).
"""

from __future__ import annotations

from app.ai.gateway import factory
from app.ai.gateway.factory import _CB_THRESHOLD, _CircuitState


def _tripped() -> _CircuitState:
    c = _CircuitState()
    for _ in range(_CB_THRESHOLD):
        c.record_failure()
    return c


def test_open_after_threshold_then_half_open_after_window(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])

    c = _tripped()
    assert c.state() == "open"
    assert c.is_open() is True

    # Advance past the recovery window — the breaker becomes HALF_OPEN.
    clock["t"] += factory._CB_RECOVERY_SECS + 1
    assert c.state() == "half_open"
    # is_open() is back-compat: HALF_OPEN is NOT "open" (it must be reachable so
    # its single probe can run).
    assert c.is_open() is False


def test_half_open_admits_exactly_one_probe(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])

    c = _tripped()
    clock["t"] += factory._CB_RECOVERY_SECS + 1
    assert c.state() == "half_open"

    # First caller wins the probe slot; concurrent callers are shed.
    assert c.acquire() is True
    assert c.acquire() is False
    assert c.acquire() is False


def test_open_circuit_refuses_all(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])

    c = _tripped()
    assert c.state() == "open"
    assert c.acquire() is False


def test_closed_circuit_admits_without_gating() -> None:
    c = _CircuitState()
    assert c.state() == "closed"
    # No single-probe gating while closed — full concurrency.
    assert c.acquire() is True
    assert c.acquire() is True


def test_successful_probe_closes_circuit(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])

    c = _tripped()
    clock["t"] += factory._CB_RECOVERY_SECS + 1
    assert c.acquire() is True  # probe admitted

    c.record_success()
    assert c.state() == "closed"
    assert c.failure_count == 0
    assert c.probe_in_flight is False


def test_failed_probe_reopens_for_another_window(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])

    c = _tripped()
    clock["t"] += factory._CB_RECOVERY_SECS + 1
    assert c.acquire() is True  # probe admitted

    # Probe fails -> released guard + re-opened window.
    c.record_failure()
    assert c.probe_in_flight is False
    assert c.state() == "open"
    # A new probe is only allowed after the NEXT window elapses.
    assert c.acquire() is False
    clock["t"] += factory._CB_RECOVERY_SECS + 1
    assert c.state() == "half_open"
    assert c.acquire() is True


def test_get_circuit_state_reports_tristate_without_consuming_probe(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(factory.time, "monotonic", lambda: clock["t"])
    factory._circuit_states.clear()

    name = "probe-provider"
    circuit = factory._get_circuit(name)
    for _ in range(_CB_THRESHOLD):
        circuit.record_failure()
    assert factory.get_circuit_state(name) == "open"

    clock["t"] += factory._CB_RECOVERY_SECS + 1
    # Reading the state must NOT consume the half-open probe slot.
    assert factory.get_circuit_state(name) == "half_open"
    assert factory.get_circuit_state(name) == "half_open"
    assert circuit.probe_in_flight is False
    # The probe is still available for a real call.
    assert circuit.acquire() is True

    factory._circuit_states.clear()
