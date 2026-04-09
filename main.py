"""Automated traffic counter ingestion and analytics module.

This module provides a streaming, memory-efficient processor for ISO-8601 annotated
vehicle traffic records. It calculates total vehicle counts, daily aggregates, top
half-hour peaks (using a Min-Heap constraint), and identifies the 1.5-hour contiguous
block with the lowest observed traffic volume.
"""

import heapq
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator


@dataclass(order=True)
class HalfHour:
    """Represents a single 30-minute interval and its logged vehicle count.

    Attributes:
        count (int): The quantity of vehicles observed.
        timestamp (datetime): The starting ISO-8601 timestamp of the interval. Excluded from
            logical comparisons, ensuring ordering is evaluated strictly by count.
    """

    count: int
    timestamp: datetime = field(compare=False)


@dataclass
class Metrics:
    """Stateful aggregator computing rolling analytics over time-series traffic logs.

    This class encapsulates data structures to maintain Total count, Daily counts, Top-3
    highest intervals, and an active sliding-window to identify the minimum contiguous
    1.5-hour (3-record) traffic block without bounding datasets in memory.

    Attributes:
        total_vehicles (int): The running total of all vehicles logged.
        daily (list[tuple[str, int]]): A list mapping iso-formatted day strings to vehicle counts.
        top_3_half_hours (list[tuple[str, int]]): A list mapping iso-formatted half-hour strings to vehicle counts, sorted by count in descending order.
        least_hour_and_half (list[tuple[str, int]]): A list mapping iso-formatted half-hour strings to vehicle counts, sorted by timestamp in ascending order.
    """

    total_vehicles: int = 0
    _daily: dict[date, int] = field(default_factory=dict)
    _top_3_half_hours: list[HalfHour] = field(default_factory=list)
    _last_hour_and_half: list[HalfHour] = field(default_factory=list, repr=False)
    _least_hour_and_half: list[HalfHour] = field(default_factory=list)

    @property
    def daily(self) -> list[tuple[str, int]]:
        """Retrieves aggregated daily vehicle totals sequentially.

        Returns:
            list[tuple[str, int]]: A list mapping iso-formatted day strings to vehicle counts.
        """
        # return sorted(self._daily.items())
        # assuming that they'd be sorted as the input would have been
        return [(d.isoformat(), c) for d, c in self._daily.items()]

    def _update_daily(self, count: int, half_hour: datetime) -> None:
        """Accumulates a single half-hour log into its respective daily total.

        Args:
            count (int): The number of vehicles in the interval.
            half_hour (datetime): The interval timestamp triggering the update.
        """
        day = half_hour.date()
        self._daily[day] = self._daily.get(day, 0) + count

    @property
    def top_3_half_hours(self) -> list[tuple[str, int]]:
        """Resolves the Top 3 highest traffic half-hours observed globally.

        Returns:
            list[tuple[str, int]]: Formatted datetime string (in secs), count pairs ordered descending by count.
        """
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._top_3_half_hours],
            key=lambda x: x[1],
            reverse=True,
        )

    def _update_top_3_half_hours(self, count: int, timestamp: datetime) -> None:
        """Maintains a bounded size-3 Min-Heap optimizing top interval lookups dynamically.

        Args:
            count (int): The number of vehicles observed.
            timestamp (datetime): The interval timestamp triggering the evaluation.
        """
        half_hour = HalfHour(count, timestamp)
        if len(self._top_3_half_hours) < 3:
            heapq.heappush(self._top_3_half_hours, half_hour)
        else:
            # given it's minheap, we get the lowest half_hour of top_3_half_hours
            lowest_half_hour = heapq.heappop(self._top_3_half_hours)
            if half_hour > lowest_half_hour:
                heapq.heappush(self._top_3_half_hours, half_hour)
            else:
                heapq.heappush(self._top_3_half_hours, lowest_half_hour)

    @property
    def last_hour_and_half(self) -> list[tuple[str, int]]:
        """Returns the current contiguous sliding window of up to three time-steps.

        Returns:
            list[tuple[str, int]]: Contiguous elements formatted chronologically by datetime string (in secs).
        """
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._last_hour_and_half],
            key=lambda x: x[0],
        )

    def _update_last_hour_and_half(self, count: int, timestamp: datetime) -> None:
        """Advances the 1.5-hour sliding window, validating explicit temporal contiguity.

        If timestamps violate the 30-minute delta restriction, the active window resets.
        If the window size exceeds 3, the oldest elements are removed.
        Update the least_hour_and_half if the current window is the least.

        Args:
            count (int): Total vehicle count for the active step.
            timestamp (datetime): Timestamp acting as the sequential stream cursor.
        """
        half_hour = HalfHour(count, timestamp)

        # reset the window if half_hour is not contiguous
        if len(self._last_hour_and_half) > 0 and half_hour.timestamp - self._last_hour_and_half[
            -1
        ].timestamp != timedelta(minutes=30):
            self._last_hour_and_half = []

        # append the new half_hour
        # either a new window of 3 half hours or append to existing window
        self._last_hour_and_half.append(half_hour)

        # if window size exceeds 3, remove the oldest element
        while len(self._last_hour_and_half) > 3:
            self._last_hour_and_half.pop(0)

        # window size will be 3, update the least_half_hour
        self._update_least_hour_and_half()
        return

    @property
    def least_hour_and_half(self) -> list[tuple[str, int]]:
        """Retrieves the exact 3-record contiguous sequence exhibiting minimum traffic.

        Returns:
            list[tuple[str, int]]: Chronologically ordered baseline records formatted.
        """
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._least_hour_and_half],
            key=lambda x: x[0],
        )

    def _update_least_hour_and_half(self) -> None:
        """Evaluates whether the current contiguous 1.5h block is the global minimum
        and updates the least_hour_and_half if it is.

        Triggers only when the `_last_hour_and_half` active window reaches a length of 3.
        """
        # update the least_half_hour with last_half_hour if it has less vehicles than the current least_half_hour
        if len(self._last_hour_and_half) == 3:
            self._least_hour_and_half = (
                self._last_hour_and_half.copy()
                if len(self._least_hour_and_half) == 0  # if least_half_hour is empty, update it
                or self.__sum_vehicles_across_hhs(self._last_hour_and_half)
                < self.__sum_vehicles_across_hhs(
                    self._least_hour_and_half
                )  # if last_half_hour has less vehicles than the current least_half_hour, update it
                else self._least_hour_and_half  # else keep the current least_half_hour
            )

    def __sum_vehicles_across_hhs(self, half_hours: list[HalfHour]) -> int:
        """Sums traffic across a specific array subset of HalfHour boundary periods.

        Args:
            half_hours (list[HalfHour]): Active window block to be aggregated.

        Returns:
            int: Explicit total car count spanning the array.
        """
        return sum(hh.count for hh in half_hours)

    def parse_half_hour_row(self, row: tuple[datetime, int]) -> None:
        """Sequentially triggers all sub-metric update loops upon ingesting a log row.

        Args:
            row (tuple[datetime, int]): A streaming payload of (timestamp, count).
        """
        half_hour = row[0]
        count = row[1]

        # update total vehicles
        self.total_vehicles += count

        # update daily
        self._update_daily(count, half_hour)

        # update top 3 half hours
        self._update_top_3_half_hours(count, half_hour)

        # update last_half_hour (in turn least_half_hour)
        self._update_last_hour_and_half(count, half_hour)

    def __generate_time_string(self, data: list[tuple[str, int]]) -> str:
        """Helper flattening key-value tuples directly into raw analytic string blocks.

        Args:
            data (list[tuple[str, int]]): Tuples containing standard format string, count.

        Returns:
            str: Flat-text newline separated visualization string.
        """
        return "\n".join([f"{d} {c}" for d, c in data])

    def __str__(self) -> str:
        """Standardizes representation cleanly isolating the core L7 metric pillars.

        Returns:
            str: Human readable aggregated report across Total, Daily, Top-3, and Least-Block.
        """
        return (
            f"total cars:\n{self.total_vehicles}\n\n"
            f"daily cars:\n{self.__generate_time_string(self.daily)}\n\n"
            f"top 3 half hours:\n{self.__generate_time_string(self.top_3_half_hours)}\n\n"
            f"least hour and half:\n{self.__generate_time_string(self.least_hour_and_half)}"
        )


def read_file_data(file_path: str) -> Iterator[tuple[datetime, int]]:
    """Yields parsed half-hour bounds strictly lazily masking disk size constraints.

    Args:
        file_path (str): Relative or absolute pointer to the traffic log source.

    Yields:
        Iterator[tuple[datetime, int]]: Streaming (timestamp, payload) event tuples.
    """
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            date_str, count_str = line.split()
            # date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            date = datetime.fromisoformat(date_str)
            count = int(count_str)
            yield date, count


def calculate_metrics(data: Iterator[tuple[datetime, int]]) -> Metrics:
    """Delegates a raw event stream generator through the bounded L7 metrics handler.

    Args:
        data (Iterator[tuple[datetime, int]]): Lazy evaluated temporal array source.

    Returns:
        Metrics: Populated and finalized statistical boundary block.
    """
    metrics = Metrics()
    for row in data:
        metrics.parse_half_hour_row(row)
    return metrics


def main() -> None:
    """Direct orchestration pipeline executing algorithmic tests systematically."""
    data = read_file_data("input.csv")
    metrics = calculate_metrics(data)
    print(metrics)


if __name__ == "__main__":
    main()
