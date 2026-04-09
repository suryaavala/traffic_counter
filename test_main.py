"""Tests for the main traffic counter module."""

import runpy
import textwrap
from datetime import datetime, timedelta
from unittest.mock import mock_open, patch

from main import HalfHour, Metrics, calculate_metrics, main, read_file_data

# =====================================================================
# 1. HalfHour Tie-Breaker Logic
# =====================================================================


def test_halfhour_tie_breaker() -> None:
    """Verifies that equal counts correctly force the newer timestamp to be 'less than'."""
    older = HalfHour(count=10, timestamp=datetime(2021, 1, 1, 10, 0))
    newer = HalfHour(count=10, timestamp=datetime(2021, 1, 1, 10, 30))

    # 10 == 10, tie breaker triggers: newer timestamp must be evaluated as "smaller"
    assert newer < older


def test_halfhour_primary_order() -> None:
    """Verifies standard count-based prioritization."""
    small = HalfHour(count=5, timestamp=datetime(2021, 1, 1, 10, 0))
    big = HalfHour(count=15, timestamp=datetime(2021, 1, 1, 9, 0))
    assert small < big


# =====================================================================
# 2. Generator Constraints (read_file_data)
# =====================================================================


def test_read_file_data_clean_skip() -> None:
    """Validates parsing skips empty lines and strips trailing data gracefully."""
    dirty_input = textwrap.dedent(
        """\

        2021-12-01T05:00:00 5    
        
        2021-12-01T05:30:00        12
        """
    )
    with patch("builtins.open", mock_open(read_data=dirty_input)):
        results = list(read_file_data("dummy.txt"))

        assert len(results) == 2
        assert results[0] == (datetime(2021, 12, 1, 5, 0), 5)
        assert results[1] == (datetime(2021, 12, 1, 5, 30), 12)


# =====================================================================
# 3. Bounded Heap Constraints (top_3_half_hours)
# =====================================================================


def test_top_3_with_fewer_than_3_records() -> None:
    """Validates top-3 extraction doesn't crash when supplied with limited inputs."""
    metrics = Metrics()
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 0), 5))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 30), 15))

    assert len(metrics.top_3_half_hours) == 2
    # Ensure descending order
    assert metrics.top_3_half_hours[0][1] == 15


def test_top_3_massive_tie() -> None:
    """Proves chronological 'older' records survive identical Top-3 capacity ties."""
    metrics = Metrics()
    t1 = datetime(2021, 1, 1, 10, 0)

    # Send 5 identical records chronologically
    for i in range(5):
        metrics.parse_half_hour_row((t1 + timedelta(minutes=30 * i), 100))

    top = metrics.top_3_half_hours
    assert len(top) == 3
    # The oldest 3 must survive. However, because they have identical counts,
    # the exact array order is determined by heap-tree traversal (unstable sort).
    # We verify exact survival using sets.
    expected = {
        ("2021-01-01T10:00:00", 100),
        ("2021-01-01T10:30:00", 100),
        ("2021-01-01T11:00:00", 100),
    }
    assert set(top) == expected


def test_top_3_ejection() -> None:
    """Tests that the exact 4th minimum rank gets properly ejected."""
    metrics = Metrics()
    # 5, 15, 10, 20
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 0), 5))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 30), 15))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 11, 0), 10))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 11, 30), 20))

    # 5 should be ejected. Remaining: 20, 15, 10
    top = metrics.top_3_half_hours
    assert len(top) == 3
    assert top[0][1] == 20
    assert top[2][1] == 10


# =====================================================================
# 4. The Sliding Window (least_hour_and_half)
# =====================================================================


def test_window_sparse_inputs() -> None:
    """Less than 3 contiguous inputs should yield empty least hour metrics."""
    metrics = Metrics()
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 0), 5))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 30), 5))
    assert metrics.least_hour_and_half == []


def test_window_disjoint_breaks() -> None:
    """Ensures window array completely purges when timestamps break contiguity."""
    metrics = Metrics()
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 0), 5))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 10, 30), 5))
    # Jump 1 hour!
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 12, 0), 5))
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 12, 30), 5))

    # Never hit 3 contiguous blocks
    assert metrics.least_hour_and_half == []


def test_window_exactly_4_shift() -> None:
    """Verifies that inserting a 4th contiguous record dynamically swaps if lower."""
    metrics = Metrics()
    base = datetime(2021, 1, 1, 10, 0)

    # A block: 10 + 10 + 10 = 30
    metrics.parse_half_hour_row((base, 10))
    metrics.parse_half_hour_row((base + timedelta(minutes=30), 10))
    metrics.parse_half_hour_row((base + timedelta(minutes=60), 10))

    assert metrics._Metrics__sum_vehicles_across_hhs(metrics._least_hour_and_half) == 30

    # Touch the last_hour_and_half property for 100% coverage
    active_window = metrics.last_hour_and_half
    assert len(active_window) == 3
    assert active_window[0][0] == "2021-01-01T10:00:00"

    # Next block is shifted: 10 + 10 + 0 = 20
    metrics.parse_half_hour_row((base + timedelta(minutes=90), 0))

    # The new minimum should be 20 from the newly shifted window
    assert sum(c for _, c in metrics.least_hour_and_half) == 20
    assert metrics.least_hour_and_half[0][0] == "2021-01-01T10:30:00"


def test_window_ties() -> None:
    """Verifies that an older 1.5-hour sequence is maintained during sum collisions."""
    metrics = Metrics()
    base = datetime(2021, 1, 1, 10, 0)

    # Block 1 (Total: 30)
    metrics.parse_half_hour_row((base, 10))
    metrics.parse_half_hour_row((base + timedelta(minutes=30), 10))
    metrics.parse_half_hour_row((base + timedelta(minutes=60), 10))

    # Break contiguity
    base2 = datetime(2021, 1, 2, 10, 0)
    # Block 2 (Total: 30)
    metrics.parse_half_hour_row((base2, 10))
    metrics.parse_half_hour_row((base2 + timedelta(minutes=30), 10))
    metrics.parse_half_hour_row((base2 + timedelta(minutes=60), 10))

    # The older block (2021-01-01) must survive
    assert metrics.least_hour_and_half[0][0] == "2021-01-01T10:00:00"


# =====================================================================
# 5. System Wide Integration Bounds
# =====================================================================


def test_integration_zero_state() -> None:
    """Validates an empty generator calculates perfectly without crashes."""
    metrics = calculate_metrics(iter([]))
    assert metrics.total_vehicles == 0
    assert metrics.daily == []
    assert metrics.top_3_half_hours == []
    assert metrics.least_hour_and_half == []

    output = str(metrics)
    assert "total cars:\n0" in output


def test_integration_midnight_shift() -> None:
    """Validates daily bounds split exactly over UTC midnight increments."""
    metrics = Metrics()
    metrics.parse_half_hour_row((datetime(2021, 1, 1, 23, 30), 10))
    metrics.parse_half_hour_row((datetime(2021, 1, 2, 0, 0), 15))
    metrics.parse_half_hour_row((datetime(2021, 1, 2, 0, 30), 5))

    assert metrics.daily == [
        ("2021-01-01", 10),
        ("2021-01-02", 20),
    ]


def test_happy_path_integration() -> None:
    """Validates the happy path execution against AIPS PDF data bounds."""
    # The literal exact input provided in the AIPS PDF
    input_data = textwrap.dedent(
        """\
        2021-12-01T05:00:00 5
        2021-12-01T05:30:00 12
        2021-12-01T06:00:00 14
        2021-12-01T06:30:00 15
        2021-12-01T07:00:00 25
        2021-12-01T07:30:00 46
        2021-12-01T08:00:00 42
        2021-12-01T15:00:00 9
        2021-12-01T15:30:00 11
        2021-12-01T23:30:00 0
        2021-12-05T09:30:00 18
        2021-12-05T10:30:00 15
        2021-12-05T11:30:00 7
        2021-12-05T12:30:00 6
        2021-12-05T13:30:00 9
        2021-12-05T14:30:00 11
        2021-12-05T15:30:00 15
        2021-12-08T18:00:00 33
        2021-12-08T19:00:00 28
        2021-12-08T20:00:00 25
        2021-12-08T21:00:00 21
        2021-12-08T22:00:00 16
        2021-12-08T23:00:00 11
        2021-12-09T00:00:00 4
        """
    )

    with patch("builtins.open", mock_open(read_data=input_data)):
        data_iterator = read_file_data("dummy_path.csv")
        metrics = calculate_metrics(data_iterator)

        # 1. Total cars expected == 398
        assert metrics.total_vehicles == 398

        # 2. Daily totals testing
        assert metrics.daily == [
            ("2021-12-01", 179),
            ("2021-12-05", 81),
            ("2021-12-08", 134),
            ("2021-12-09", 4),
        ]

        # 3. Top 3 half hours testing (descending counts)
        assert metrics.top_3_half_hours == [
            ("2021-12-01T07:30:00", 46),
            ("2021-12-01T08:00:00", 42),
            ("2021-12-08T18:00:00", 33),
        ]

        # 4. Least 1.5 Hour Window (contiguous)
        assert metrics.least_hour_and_half == [
            ("2021-12-01T05:00:00", 5),
            ("2021-12-01T05:30:00", 12),
            ("2021-12-01T06:00:00", 14),
        ]


# =====================================================================
# 6. Top-Level Execution Targets (__main__)
# =====================================================================


def test_main_function() -> None:
    """Executes the `main()` orchestration boundary securely capturing stdout."""
    with patch("builtins.print") as mock_print:
        main()
        mock_print.assert_called_once()
        args = mock_print.call_args[0][0]
        # Validates it actually printed the `Metrics` string
        assert "total cars:" in str(args)


def test_module_execution() -> None:
    """Validates the standard `__name__ == '__main__'` block execution."""
    with patch("builtins.print"):
        # Execute it securely exactly as Python does when triggered via CLI
        result = runpy.run_module("main", run_name="__main__")
        assert "main" in result
