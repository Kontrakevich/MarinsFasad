from __future__ import annotations

import os
import time
from typing import Any

import requests

from . import ai_engine as _engine_module
from .hybrid_engine import AIEngineError
from .skill_engine import OpenRouterImageEngine as _SkillOpenRouterImageEngine


class OpenRouterImageEngine(_SkillOpenRouterImageEngine):
    """Final runtime transport resilience layer.

    Retries only transient gateway/network failures. Semantic request failures
    remain owned by the existing transport logic (for example provider-size 400
    and request-size 413 handling).
    """

    transient_provider_statuses = frozenset({408, 425, 429, 500, 502, 503, 504})
    provider_retry_max_attempts = 4
    provider_retry_policy = "transient-gateway-network-exponential-backoff-v1"

    @staticmethod
    def _retry_delay(attempt: int, response: requests.Response | None = None) -> float:
        if response is not None:
            retry_after = str(response.headers.get("Retry-After") or "").strip()
            try:
                if retry_after:
                    return max(0.0, min(8.0, float(retry_after)))
            except ValueError:
                pass
        return min(4.0, 0.65 * (2 ** max(0, attempt - 1)))

    def _retry_log(self) -> list[dict[str, Any]]:
        log = getattr(self._runtime, "provider_transient_retries", None)
        if log is None:
            log = []
            self._runtime.provider_transient_retries = log
        return log

    def _send_prepared(self, prepared_request: requests.PreparedRequest) -> requests.Response:
        configured = int(os.getenv("OPENROUTER_TRANSIENT_MAX_ATTEMPTS", "0") or 0)
        max_attempts = configured if configured > 0 else self.provider_retry_max_attempts
        max_attempts = max(1, min(6, max_attempts))
        log = self._retry_log()

        for attempt in range(1, max_attempts + 1):
            try:
                response = super()._send_prepared(prepared_request)
            except (requests.Timeout, requests.ConnectionError) as exc:
                entry = {
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "kind": "network",
                    "error_type": type(exc).__name__,
                }
                log.append(entry)
                if attempt >= max_attempts:
                    raise AIEngineError(
                        "OpenRouter connection failed after transient retries",
                        details={
                            "reason": "provider_network_retries_exhausted",
                            "provider_transient_retries": list(log),
                        },
                    ) from exc
                delay = self._retry_delay(attempt)
                entry["delay_seconds"] = delay
                time.sleep(delay)
                continue

            if response.status_code not in self.transient_provider_statuses:
                return response

            entry = {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "kind": "http",
                "status": int(response.status_code),
                "response_excerpt": str(response.text or "")[:400],
            }
            log.append(entry)
            if attempt >= max_attempts:
                return response

            delay = self._retry_delay(attempt, response)
            entry["delay_seconds"] = delay
            time.sleep(delay)

        raise AIEngineError(
            "OpenRouter transient retry loop ended unexpectedly",
            details={"reason": "provider_retry_internal_error"},
        )

    def generate_environment(self, **kwargs) -> dict:
        self._runtime.provider_transient_retries = []
        try:
            result = super().generate_environment(**kwargs)
        except AIEngineError as exc:
            retries = list(getattr(self._runtime, "provider_transient_retries", []) or [])
            if not retries:
                raise
            details = dict(getattr(exc, "details", {}) or {})
            details["provider_retry_policy"] = self.provider_retry_policy
            details["provider_transient_retries"] = retries
            details["provider_retry_count"] = len(retries)
            raise AIEngineError(str(exc), details=details) from exc

        retries = list(getattr(self._runtime, "provider_transient_retries", []) or [])
        result["provider_retry_policy"] = self.provider_retry_policy
        result["provider_transient_retries"] = retries
        result["provider_retry_count"] = len(retries)
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
