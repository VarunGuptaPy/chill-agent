"""Retry decorator with exponential backoff for all external API calls."""

from __future__ import annotations

import functools
import time
from typing import Callable, Tuple, Type

import structlog

logger = structlog.get_logger()


def with_retry(
    attempts: int = 3,
    backoff: Tuple[float, ...] = (2.0, 8.0, 30.0),
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: retry `attempts` times with given backoff seconds on exception.

    Usage:
        @with_retry(attempts=3, backoff=(2, 8, 30))
        def call_api(): ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts:
                        wait = backoff[min(attempt - 1, len(backoff) - 1)]
                        logger.warning(
                            "api_call_failed_retrying",
                            function=fn.__name__,
                            attempt=attempt,
                            wait_seconds=wait,
                            error=str(exc),
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "api_call_failed_final",
                            function=fn.__name__,
                            attempts=attempts,
                            error=str(exc),
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def with_retry_async(
    attempts: int = 3,
    backoff: Tuple[float, ...] = (2.0, 8.0, 30.0),
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Async version of with_retry."""
    import asyncio

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts:
                        wait = backoff[min(attempt - 1, len(backoff) - 1)]
                        logger.warning(
                            "async_api_call_failed_retrying",
                            function=fn.__name__,
                            attempt=attempt,
                            wait_seconds=wait,
                            error=str(exc),
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "async_api_call_failed_final",
                            function=fn.__name__,
                            attempts=attempts,
                            error=str(exc),
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
