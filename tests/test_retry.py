from __future__ import annotations

from typing import Any

import httpx
import pytest

from captures_to_md.retry import call_with_retry


def _make_http_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.extend.ai/parse")
    response = httpx.Response(status, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_retries_on_429_and_succeeds() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _make_http_error(429)
        return "ok"

    result = call_with_retry(
        fn,
        description="upload",
        max_attempts=5,
        base_seconds=0.01,
        cap_seconds=0.1,
        sleep=sleeps.append,
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_honors_retry_after_header() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _make_http_error(429, headers={"Retry-After": "0.05"})
        return "ok"

    call_with_retry(
        fn,
        description="upload",
        max_attempts=5,
        base_seconds=10.0,
        cap_seconds=100.0,
        sleep=sleeps.append,
    )
    assert sleeps == [pytest.approx(0.05)]


def test_non_retryable_raises_immediately() -> None:
    def fn() -> str:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        call_with_retry(
            fn,
            description="parse",
            max_attempts=5,
            base_seconds=0.0,
            cap_seconds=0.0,
        )


def test_type_error_never_retried_even_when_message_mentions_timeout() -> None:
    """SDK signature mismatches raise TypeError with 'timeout' in the message —
    the old heuristic would retry those uselessly."""
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise TypeError("got an unexpected keyword argument 'timeout'")

    with pytest.raises(TypeError):
        call_with_retry(
            fn,
            description="parse",
            max_attempts=5,
            base_seconds=0.0,
            cap_seconds=0.0,
            sleep=lambda _s: None,
        )
    assert calls["n"] == 1


def test_gives_up_after_max_attempts() -> None:
    def fn() -> Any:
        raise _make_http_error(500)

    with pytest.raises(httpx.HTTPStatusError):
        call_with_retry(
            fn,
            description="upload",
            max_attempts=3,
            base_seconds=0.0,
            cap_seconds=0.0,
            sleep=lambda _s: None,
        )
