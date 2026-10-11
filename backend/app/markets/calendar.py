"""Trading calendars: which bar timestamps exist, and where forecast horizons land.

Everything that assumes "24/7, one bar every hour, a day is 86,400 seconds" lives
here, so a market with sessions, weekends or holidays can supply its own rules.
"""

from datetime import timedelta
import pandas as pd

DAY = 86400


class ContinuousCalendar:
    """A market that trades every interval of every day (crypto spot).

    Daily forecast origins sit at 00:00 UTC and horizon ``d`` is exactly ``d``
    calendar days later, so targets are always bars that should exist.
    """

    kind = "continuous"
    description = "24/7, no sessions or holidays"

    def __init__(self, interval_seconds=3600):
        if interval_seconds <= 0 or DAY % interval_seconds:
            raise ValueError("Interval must divide one day")
        self.interval_seconds = int(interval_seconds)

    def expected_open_times(self, start, end):
        """Every bar open time in the half-open range [start, end)."""
        return pd.date_range(
            start=start,
            end=end - timedelta(seconds=self.interval_seconds),
            freq=f"{self.interval_seconds}s",
            tz="UTC",
        )

    def expected_count(self, start, end):
        return int((end - start).total_seconds() // self.interval_seconds)

    def misaligned(self, open_times):
        """Boolean mask of open times that do not start exactly on a bar boundary."""
        return open_times.dt.floor(f"{self.interval_seconds}s") != open_times

    def is_origin(self, t):
        """True when a completed-bar time (unix seconds) is a daily forecast origin."""
        return t % DAY == 0

    def origins(self, start, end):
        """Scheduled daily origins in [start, end), whether or not data exists."""
        first = -(-int(start) // DAY) * DAY
        return list(range(first, int(end), DAY))

    def horizon_target(self, origin, step):
        """Unix time of the bar close ``step`` forecast days after ``origin``."""
        return origin + step * DAY

    def horizon_hours(self, step):
        return step * 24

    def lookback_bars(self, days):
        """Bars in a look-back of ``days`` calendar days, origin bar included."""
        return days * DAY // self.interval_seconds + 1
