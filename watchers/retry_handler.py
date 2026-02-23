"""retry_handler.py - Exponential backoff retry logic for AI Employee watchers.

Gold Tier: Error recovery and graceful degradation.
"""

import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class TransientError(Exception):
    """Raised for temporary, retryable failures (network timeouts, rate limits, etc.)."""
    pass


class AuthenticationError(Exception):
    """Raised for authentication failures — requires human intervention."""
    pass


class DataError(Exception):
    """Raised for corrupted or malformed data — quarantine and alert."""
    pass


def with_retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """
    Decorator: retry a function on TransientError with exponential backoff.

    Usage:
        @with_retry(max_attempts=3, base_delay=2.0)
        def fetch_emails():
            ...

    Args:
        max_attempts: Total attempts before giving up.
        base_delay:   Initial wait between retries (seconds).
        max_delay:    Cap for exponential backoff (seconds).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except TransientError as e:
                    last_exc = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[retry] {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                except (AuthenticationError, DataError):
                    # Non-retryable — propagate immediately
                    raise
            raise last_exc  # should never reach here
        return wrapper
    return decorator


def retry_once(func):
    """Simple one-retry decorator (convenience wrapper)."""
    return with_retry(max_attempts=2, base_delay=5.0)(func)


class CircuitBreaker:
    """
    Circuit breaker pattern for external service calls.

    States:
      CLOSED   → normal operation
      OPEN     → service is down, reject calls immediately
      HALF_OPEN → test if service recovered

    Usage:
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        if cb.can_proceed():
            try:
                result = call_external_service()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
                raise
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self):
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                logger.info("[circuit_breaker] State → HALF_OPEN (testing recovery)")
        return self._state

    def can_proceed(self) -> bool:
        return self.state in (self.CLOSED, self.HALF_OPEN)

    def record_success(self):
        self._failure_count = 0
        if self._state != self.CLOSED:
            logger.info("[circuit_breaker] State → CLOSED (service recovered)")
        self._state = self.CLOSED

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            if self._state != self.OPEN:
                logger.warning(
                    f"[circuit_breaker] State → OPEN after {self._failure_count} failures. "
                    f"Recovery in {self.recovery_timeout}s."
                )
            self._state = self.OPEN


class RateLimiter:
    """
    Simple token-bucket rate limiter to cap actions per hour.

    Usage:
        limiter = RateLimiter(max_per_hour=10)
        if limiter.allow():
            send_email(...)
    """

    def __init__(self, max_per_hour: int = 10):
        self.max_per_hour = max_per_hour
        self._tokens = max_per_hour
        self._last_refill = time.time()

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self._last_refill
        # Refill proportionally (token bucket)
        refill = (elapsed / 3600.0) * self.max_per_hour
        if refill > 0:
            self._tokens = min(self.max_per_hour, self._tokens + refill)
            self._last_refill = now

        if self._tokens >= 1:
            self._tokens -= 1
            return True

        logger.warning(
            f"[rate_limiter] Rate limit reached ({self.max_per_hour}/hr). Action blocked."
        )
        return False
