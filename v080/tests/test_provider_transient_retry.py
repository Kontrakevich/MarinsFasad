import requests

from app.ai_engine import OpenRouterImageEngine
from app.hybrid_engine import AIEngineError
import app.provider_retry as retry_module
from app.skill_engine import OpenRouterImageEngine as SkillEngine


def _response(status: int, text: str = "") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = text.encode("utf-8")
    response.headers["Content-Type"] = "text/plain"
    return response


def test_transient_502_retries_until_success(monkeypatch) -> None:
    engine = OpenRouterImageEngine()
    calls = []
    responses = [_response(502, "temporary gateway"), _response(502, "temporary gateway"), _response(200, "ok")]

    def fake_send(self, prepared_request):
        calls.append(prepared_request)
        return responses.pop(0)

    monkeypatch.setattr(SkillEngine, "_send_prepared", fake_send)
    monkeypatch.setattr(retry_module.time, "sleep", lambda _: None)

    result = engine._send_prepared(requests.Request("POST", "https://example.test").prepare())

    assert result.status_code == 200
    assert len(calls) == 3
    log = engine._retry_log()
    assert [item["status"] for item in log] == [502, 502]
    assert engine.provider_retry_policy == "transient-gateway-network-exponential-backoff-v1"


def test_non_transient_400_is_not_retried(monkeypatch) -> None:
    engine = OpenRouterImageEngine()
    calls = 0

    def fake_send(self, prepared_request):
        nonlocal calls
        calls += 1
        return _response(400, "bad request")

    monkeypatch.setattr(SkillEngine, "_send_prepared", fake_send)
    monkeypatch.setattr(retry_module.time, "sleep", lambda _: None)

    result = engine._send_prepared(requests.Request("POST", "https://example.test").prepare())

    assert result.status_code == 400
    assert calls == 1
    assert engine._retry_log() == []


def test_network_timeout_retries_and_reports_exhaustion(monkeypatch) -> None:
    engine = OpenRouterImageEngine()
    calls = 0

    def fake_send(self, prepared_request):
        nonlocal calls
        calls += 1
        raise requests.Timeout("temporary timeout")

    monkeypatch.setattr(SkillEngine, "_send_prepared", fake_send)
    monkeypatch.setattr(retry_module.time, "sleep", lambda _: None)
    monkeypatch.setenv("OPENROUTER_TRANSIENT_MAX_ATTEMPTS", "3")

    try:
        engine._send_prepared(requests.Request("POST", "https://example.test").prepare())
    except AIEngineError as exc:
        assert exc.details["reason"] == "provider_network_retries_exhausted"
        assert len(exc.details["provider_transient_retries"]) == 3
    else:
        raise AssertionError("AIEngineError expected")

    assert calls == 3


def test_provider_root_cause_stays_visible_after_single_pass_wrapper(monkeypatch) -> None:
    engine = OpenRouterImageEngine()

    def fake_single_pass(self, **kwargs):
        raise AIEngineError(
            "Nano Banana не смогла выполнить генерацию через OpenRouter. Подробности сохранены в диагностике.",
            details={"provider_error": "OpenRouter 502: upstream unavailable"},
        )

    monkeypatch.setattr(SkillEngine, "_single_pass", fake_single_pass)

    try:
        engine._single_pass(prompt="test")
    except AIEngineError as exc:
        assert str(exc) == "Nano Banana / OpenRouter: OpenRouter 502: upstream unavailable"
        assert exc.details["provider_error"].startswith("OpenRouter 502")
    else:
        raise AssertionError("AIEngineError expected")


def test_active_runtime_is_retry_wrapper() -> None:
    engine = OpenRouterImageEngine()
    assert engine.transient_provider_statuses == frozenset({408, 425, 429, 500, 502, 503, 504})
    assert engine.provider_retry_max_attempts == 4
    assert engine.transport_engine_version == "3.4.0"
