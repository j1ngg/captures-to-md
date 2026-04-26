from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

import httpx

log = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableError(Exception):
    """Wrap an underlying SDK/transport error as retryable."""


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    header = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        return None


_NEVER_RETRY = (
    TypeError,
    AttributeError,
    NameError,
    ValueError,
    KeyError,
    ImportError,
)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _NEVER_RETRY):
        return False
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException, RetryableError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return True
    msg = str(exc).lower()
    if "rate limit" in msg or "too many requests" in msg:
        return True
    return False


def _is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def call_with_retry(
    fn: Callable[[], T],
    *,
    description: str,
    max_attempts: int,
    base_seconds: float,
    cap_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Invoke ``fn`` with exponential backoff + jitter on retryable errors."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable(exc) or attempt + 1 >= max_attempts:
                raise
            retry_after = _retry_after_seconds(exc) if _is_rate_limit(exc) else None
            if retry_after is not None:
                delay = min(cap_seconds, retry_after)
            else:
                delay = min(cap_seconds, base_seconds * (2**attempt))
                delay += random.uniform(0, base_seconds)
            log.warning(
                "%s failed (%s); retry %d/%d in %.1fs",
                description,
                type(exc).__name__,
                attempt + 1,
                max_attempts - 1,
                delay,
            )
            sleep(delay)
            attempt += 1
