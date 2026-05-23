"""
Resilience utilities for trading-triggers.

Provides retry decorators for Yahoo Finance API calls and a circuit breaker
for Discord webhook notifications.
"""

import logging
from datetime import datetime, UTC
from typing import Any, Callable, TypeVar

from tenacity import (
    retry as tenacity_retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and a call is blocked."""
    pass

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_yfinance(func: F) -> F:
    """Decorator that retries yfinance calls with exponential backoff.

    Retries up to 3 times, waiting between 4 and 10 seconds using
    exponential backoff (multiplier=1).
    """
    return tenacity_retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )(func)


class CircuitBreaker:
    """Simple circuit breaker for Discord webhook calls.

    Opens after 3 consecutive failures, stays open for 5 minutes.
    After 15 minutes it fully resets the failure count.
    """

    FAILURE_THRESHOLD = 3
    OPEN_DURATION_SECONDS = 300  # 5 minutes
    RESET_AFTER_SECONDS = 900  # 15 minutes

    def __init__(self) -> None:
        self.consecutive_failures: int = 0
        self.last_failure_time: datetime | None = None
        self.opened_at: datetime | None = None
        self.is_open: bool = False

    def record_failure(self) -> None:
        """Record a failure and open the circuit if threshold is reached."""
        now = datetime.now(UTC)
        self.last_failure_time = now
        self.consecutive_failures += 1

        if self.consecutive_failures >= self.FAILURE_THRESHOLD:
            if not self.is_open:
                self.is_open = True
                self.opened_at = now
                logger.warning(
                    "Circuit breaker OPENED after %d consecutive failures. "
                    "Waiting %d seconds before allowing calls again.",
                    self.consecutive_failures,
                    self.OPEN_DURATION_SECONDS,
                )
            else:
                logger.warning(
                    "Circuit breaker remains OPEN (%d consecutive failures).",
                    self.consecutive_failures,
                )
        else:
            logger.warning(
                "Discord webhook failure %d/%d.",
                self.consecutive_failures,
                self.FAILURE_THRESHOLD,
            )

    def record_success(self) -> None:
        """Record a success and reset failure state."""
        if self.consecutive_failures > 0 or self.is_open:
            logger.info(
                "Discord webhook success — resetting circuit breaker (%d → 0 failures).",
                self.consecutive_failures,
            )
        self.consecutive_failures = 0
        self.is_open = False
        self.opened_at = None
        self.last_failure_time = None

    def can_execute(self) -> bool:
        """Return True if the call is allowed to proceed."""
        now = datetime.now(UTC)

        # Full reset after 15 minutes of inactivity
        if self.last_failure_time is not None:
            elapsed = (now - self.last_failure_time).total_seconds()
            if elapsed >= self.RESET_AFTER_SECONDS:
                if self.consecutive_failures > 0 or self.is_open:
                    logger.info(
                        "Circuit breaker fully reset after %d seconds of inactivity.",
                        self.RESET_AFTER_SECONDS,
                    )
                self.consecutive_failures = 0
                self.is_open = False
                self.opened_at = None
                self.last_failure_time = None
                return True

        if not self.is_open:
            return True

        # Circuit is open — check if timeout has elapsed
        assert self.opened_at is not None
        elapsed = (now - self.opened_at).total_seconds()
        if elapsed >= self.OPEN_DURATION_SECONDS:
            logger.info(
                "Circuit breaker half-open: allowing one test call after %d seconds.",
                elapsed,
            )
            return True

        logger.warning(
            "Circuit breaker is OPEN: blocking call (%d/%d seconds remaining).",
            int(self.OPEN_DURATION_SECONDS - elapsed),
            self.OPEN_DURATION_SECONDS,
        )
        return False


discord_circuit_breaker = CircuitBreaker()
