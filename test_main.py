"""Tests for the main traffic counter module."""

import textwrap
from unittest.mock import mock_open, patch

from main import calculate_metrics, read_file_data


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
        data_iterator = read_file_data("dummy_path.txt")
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
