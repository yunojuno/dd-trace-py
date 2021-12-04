import threading

from ..internal import compat


cdef class RateLimiter(object):
    """
    A token bucket rate limiter implementation
    """

    cdef readonly int rate_limit
    cdef readonly float tokens
    cdef readonly int max_tokens
    cdef readonly float last_update
    cdef readonly float current_window
    cdef readonly int tokens_allowed
    cdef readonly int tokens_total
    cdef readonly float prev_window_rate
    cdef object _lock

    def __init__(self, int rate_limit):
        # type: (int) -> None
        """
        Constructor for RateLimiter

        :param rate_limit: The rate limit to apply for number of requests per second.
            rate limit > 0 max number of requests to allow per second,
            rate limit == 0 to disallow all requests,
            rate limit < 0 to allow all requests
        :type rate_limit: :obj:`int`
        """
        self.rate_limit = rate_limit
        self.tokens = rate_limit
        self.max_tokens = rate_limit

        self.last_update = compat.monotonic()

        self.current_window = 0
        self.tokens_allowed = 0
        self.tokens_total = 0
        self.prev_window_rate = -1

        self._lock = threading.Lock()

    cpdef bint is_allowed(self):
        # type: () -> bool
        """
        Check whether the current request is allowed or not

        This method will also reduce the number of available tokens by 1

        :returns: Whether the current request is allowed or not
        :rtype: :obj:`bool`
        """
        # Determine if it is allowed
        cdef bint allowed = self._is_allowed()
        # Update counts used to determine effective rate
        self._update_rate_counts(allowed)
        return allowed

    cdef void _update_rate_counts(self, bint allowed):
        # type: (bool) -> None
        cdef float now = compat.monotonic()

        # No tokens have been seen yet, start a new window
        if not self.current_window:
            self.current_window = now

        # If more than 1 second has past since last window, reset
        elif now - self.current_window >= 1.0:
            # Store previous window's rate to average with current for `.effective_rate`
            self.prev_window_rate = self._current_window_rate()
            self.tokens_allowed = 0
            self.tokens_total = 0
            self.current_window = now

        # Keep track of total tokens seen vs allowed
        if allowed:
            self.tokens_allowed += 1
        self.tokens_total += 1

    cdef bint _is_allowed(self):
        # type: () -> bool
        # Rate limit of 0 blocks everything
        if self.rate_limit == 0:
            return False

        # Negative rate limit disables rate limiting
        elif self.rate_limit < 0:
            return True

        # Lock, we need this to be thread safe, it should be shared by all threads
        with self._lock:
            self._replenish()

            if self.tokens >= 1:
                self.tokens -= 1
                return True

            return False

    cdef void _replenish(self):
        # type: () -> None
        cdef float now
        cdef float elapsed

        # If we are at the max, we do not need to add any more
        if self.tokens == self.max_tokens:
            return

        # Add more available tokens based on how much time has passed
        now = compat.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        # Update the number of available tokens, but ensure we do not exceed the max
        self.tokens = min(
            self.max_tokens,
            self.tokens + (elapsed * self.rate_limit),
        )

    cdef float _current_window_rate(self):
        # type: () -> float
        # No tokens have been seen, effectively 100% sample rate
        # DEV: This is to avoid division by zero error
        if not self.tokens_total:
            return 1.0

        # Get rate of tokens allowed
        return self.tokens_allowed / self.tokens_total

    @property
    def effective_rate(self):
        # type: () -> float
        """
        Return the effective sample rate of this rate limiter

        :returns: Effective sample rate value 0.0 <= rate <= 1.0
        :rtype: :obj:`float``
        """
        # No need to compute when the results are static
        if self.rate_limit == 0:
            return 0.0
        elif self.rate_limit < 0:
            return 1.0

        # If we have not had a previous window yet, return current rate
        if self.prev_window_rate < 0:
            return self._current_window_rate()

        return (self._current_window_rate() + self.prev_window_rate) / 2.0

    def __repr__(self):
        return "{}(rate_limit={!r}, tokens={!r}, last_update={!r}, effective_rate={!r})".format(
            self.__class__.__name__,
            self.rate_limit,
            self.tokens,
            self.last_update,
            self.effective_rate,
        )

    __str__ = __repr__
