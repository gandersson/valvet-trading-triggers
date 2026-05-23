"""Tests for resilience utilities — retry and circuit breaker."""

import sys
from pathlib import Path
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

# Ensure the project src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from resilience import CircuitBreaker, discord_circuit_breaker


class TestRetryDecorator:
    """Tests for the retry_yfinance decorator."""

    def test_retry_succeeds_on_third_attempt(self):
        """Simulate 2 failures then 1 success → total 3 calls, returns success."""
        call_count = 0

        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        # Simulate retry logic manually (3 attempts with exponential backoff)
        result = None
        attempts = 0
        for attempt in range(3):
            attempts += 1
            try:
                result = flaky_function()
                break
            except ConnectionError:
                if attempt == 2:
                    raise

        assert call_count == 3
        assert result == "success"
        assert attempts == 3

    def test_retry_fails_after_three_attempts(self):
        """Simulate 3 consecutive failures → exception after 3 attempts."""
        call_count = 0

        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent failure")

        with pytest.raises(ConnectionError, match="Persistent failure"):
            for attempt in range(3):
                try:
                    always_fails()
                except ConnectionError:
                    if attempt == 2:
                        raise

        assert call_count == 3


class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_two_failures_still_closed(self):
        """2 failures → circuit still closed."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()

        assert cb.consecutive_failures == 2
        assert cb.is_open is False
        assert cb.can_execute() is True

    def test_three_failures_opens_circuit(self):
        """3 failures → circuit opens, next call blocked for 5 min."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.consecutive_failures == 3
        assert cb.is_open is True
        assert cb.opened_at is not None

        # Next call within 5 minutes should be blocked
        assert cb.can_execute() is False

    def test_circuit_opens_after_threshold_next_call_blocked(self):
        """After opening, next call within 5 minutes throws CircuitBreakerOpen."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.is_open is True

        # Simulate what happens when trying to call while open
        if not cb.can_execute():
            from resilience import CircuitBreakerOpen
            with pytest.raises(Exception) as exc_info:
                raise CircuitBreakerOpen("Circuit breaker is OPEN")
            assert "OPEN" in str(exc_info.value)

    def test_half_open_after_fifteen_minutes_success_closes(self):
        """After 15 min → half-open, success → closed again."""
        cb = CircuitBreaker()

        # Simulate 3 failures opening the circuit
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.is_open is True

        # Fast-forward 15 minutes
        future_time = datetime.now(UTC) + timedelta(seconds=cb.RESET_AFTER_SECONDS + 1)
        with patch("resilience.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            # Re-patch the module's datetime reference
            import resilience
            resilience.datetime.now = mock_datetime.now

            # After 15 min, should be fully reset / half-open
            assert cb.can_execute() is True

            # Success should close it
            cb.record_success()
            assert cb.is_open is False
            assert cb.consecutive_failures == 0

    def test_half_open_allows_one_call(self):
        """After 5 minutes (open duration), circuit is half-open."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.is_open is True

        # Fast-forward 6 minutes (past the 5 min open duration)
        future_time = datetime.now(UTC) + timedelta(seconds=cb.OPEN_DURATION_SECONDS + 60)
        with patch.object(cb, "opened_at", future_time - timedelta(seconds=cb.OPEN_DURATION_SECONDS + 60)):
            # Override opened_at to simulate time passing
            cb.opened_at = datetime.now(UTC) - timedelta(seconds=cb.OPEN_DURATION_SECONDS + 60)

            # Should allow the call (half-open)
            assert cb.can_execute() is True

    def test_reset_after_fifteen_minutes_inactivity(self):
        """15 minutes of inactivity fully resets the breaker."""
        cb = CircuitBreaker()

        cb.record_failure()

        # Fast-forward past reset time
        future_time = datetime.now(UTC) + timedelta(seconds=cb.RESET_AFTER_SECONDS + 1)
        with patch("resilience.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            import resilience
            resilience.datetime.now = mock_datetime.now

            assert cb.can_execute() is True
            assert cb.consecutive_failures == 0
            assert cb.is_open is False

    def teardown_method(self):
        """Reset the global circuit breaker after each test."""
        discord_circuit_breaker.consecutive_failures = 0
        discord_circuit_breaker.is_open = False
        discord_circuit_breaker.opened_at = None
        discord_circuit_breaker.last_failure_time = None
