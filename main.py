import heapq
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator


@dataclass(order=True)
class HalfHour:
    count: int
    timestamp: datetime = field(compare=False)


@dataclass
class Metrics:
    total_vehicles: int = 0
    _daily: dict[date, int] = field(default_factory=dict)
    _top_3_half_hours: list[HalfHour] = field(default_factory=list)
    _last_hour_and_half: list[HalfHour] = field(default_factory=list, repr=False)
    _least_hour_and_half: list[HalfHour] = field(default_factory=list)

    @property
    def daily(self) -> list[tuple[str, int]]:
        # return sorted(self._daily.items())
        # assuming that they'd be sorted as the input would have been
        return [(d.isoformat(), c) for d, c in self._daily.items()]

    def _update_daily(self, count: int, half_hour: datetime) -> None:
        day = half_hour.date()
        self._daily[day] = self._daily.get(day, 0) + count

    @property
    def top_3_half_hours(self) -> list[tuple[str, int]]:
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._top_3_half_hours],
            key=lambda x: x[1],
            reverse=True,
        )

    def _update_top_3_half_hours(self, count: int, timestamp: datetime) -> None:
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
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._last_hour_and_half],
            key=lambda x: x[1],
        )

    def _update_last_hour_and_half(self, count: int, timestamp: datetime) -> None:
        half_hour = HalfHour(count, timestamp)

        # # if empty create a window & append half_hour
        # if len(self._last_hour_and_half) == 0:
        #     self._last_hour_and_half.append(half_hour)
        #     return

        # # if current half_hour is not contiguous, reset the window
        # if half_hour.timestamp - self._last_hour_and_half[-1].timestamp != timedelta(
        #     minutes=30
        # ):
        #     self._last_hour_and_half = []
        #     self._last_hour_and_half.append(half_hour)
        #     return

        # # if  current half_hour is contiguous and less than 3 items, append
        # if len(self._last_hour_and_half) < 3:
        #     self._last_hour_and_half.append(half_hour)
        #     return

        # # if  current half_hour is contiguous and has 3 items, check if the current half_hour has less vehicles than the oldest element in the window
        # oldest_half_hour = self._last_hour_and_half[0]
        # if half_hour.count < oldest_half_hour.count:
        #     self._last_hour_and_half.pop(0)
        #     self._last_hour_and_half.append(half_hour)

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
        return sorted(
            [(hh.timestamp.isoformat(timespec="seconds"), hh.count) for hh in self._least_hour_and_half],
            key=lambda x: x[0],
        )

    def _update_least_hour_and_half(self) -> None:
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
        return sum(hh.count for hh in half_hours)

    def parse_half_hour_row(self, row: tuple[datetime, int]) -> None:
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
        return "\n".join([f"{d} {c}" for d, c in data])

    def __str__(self) -> str:
        return (
            f"total cars:\n{self.total_vehicles}\n\n"
            f"daily cars:\n{self.__generate_time_string(self.daily)}\n\n"
            f"top 3 half hours:\n{self.__generate_time_string(self.top_3_half_hours)}\n\n"
            f"least hour and half:\n{self.__generate_time_string(self.least_hour_and_half)}"
        )


def read_file_data(file_path: str) -> Iterator[tuple[datetime, int]]:
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
    metrics = Metrics()
    for row in data:
        metrics.parse_half_hour_row(row)
    return metrics


def main() -> None:
    data = read_file_data("input.csv")
    metrics = calculate_metrics(data)
    print(metrics)


if __name__ == "__main__":
    main()
