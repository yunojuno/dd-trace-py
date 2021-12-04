import bm

from ddtrace.internal.rate_limiter import RateLimiter


class RateLimiterScenario(bm.Scenario):
    rate_limit = bm.var(type=int)

    def run(self):
        limiter = RateLimiter(self.rate_limit)

        def _(loops):
            for _ in range(loops):
                # When sampling spans we will always call `.is_allowed()` and `.effective_rate`
                limiter.is_allowed()
                limiter.effective_rate

        yield _
