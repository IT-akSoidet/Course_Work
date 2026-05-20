from datetime import time

from app.services.free_slots import (
    FreeWindow,
    MIN_WINDOW_MINUTES,
    WORK_DAY_END,
    WORK_DAY_START,
    compute_free_windows,
    find_window_for,
    format_windows,
)


def t(hh: int, mm: int = 0) -> time:
    return time(hh, mm)


def test_empty_busy_full_day_free() -> None:
    result = compute_free_windows([])
    assert result == [FreeWindow(WORK_DAY_START, WORK_DAY_END)]


def test_single_busy_in_middle() -> None:
    result = compute_free_windows([(t(11), t(12, 30))])
    assert result == [
        FreeWindow(t(8), t(11)),
        FreeWindow(t(12, 30), t(21)),
    ]


def test_multiple_busy_intervals_sorted() -> None:
    busy = [(t(11, 10), t(12, 40)), (t(9, 30), t(11)), (t(15), t(16, 30))]
    result = compute_free_windows(busy)
    assert result == [
        FreeWindow(t(8), t(9, 30)),
        FreeWindow(t(12, 40), t(15)),
        FreeWindow(t(16, 30), t(21)),
    ]


def test_overlapping_busy_merged() -> None:
    result = compute_free_windows([(t(9), t(11)), (t(10, 30), t(12))])
    assert result == [
        FreeWindow(t(8), t(9)),
        FreeWindow(t(12), t(21)),
    ]


def test_busy_outside_workday_ignored() -> None:
    result = compute_free_windows([(t(6), t(7, 30)), (t(22), t(23))])
    assert result == [FreeWindow(WORK_DAY_START, WORK_DAY_END)]


def test_busy_clipped_to_workday() -> None:
    result = compute_free_windows([(t(7), t(9))])
    assert result == [FreeWindow(t(9), t(21))]


def test_short_gap_filtered_out() -> None:
    # Busy 08:00-10:00 and 10:20-21:00 → only gap is 10:00-10:20 (20 min < 30)
    result = compute_free_windows([(t(8), t(10)), (t(10, 20), t(21))])
    assert result == []


def test_short_gap_dropped_long_gap_kept() -> None:
    # 9:00-9:20 short gap (dropped), 13:00-21:00 kept
    busy = [(t(8), t(9)), (t(9, 20), t(13))]
    result = compute_free_windows(busy)
    times = [(w.start, w.end) for w in result]
    assert (t(9), t(9, 20)) not in times
    assert (t(13), t(21)) in times


def test_min_window_threshold_constant() -> None:
    assert MIN_WINDOW_MINUTES == 30


def test_fully_busy_returns_empty() -> None:
    result = compute_free_windows([(t(8), t(21))])
    assert result == []


def test_find_window_for_inside() -> None:
    windows = [FreeWindow(t(8), t(11)), FreeWindow(t(14), t(18))]
    assert find_window_for(windows, t(15), t(17)) == FreeWindow(t(14), t(18))


def test_find_window_for_straddling() -> None:
    windows = [FreeWindow(t(8), t(11)), FreeWindow(t(14), t(18))]
    assert find_window_for(windows, t(10), t(15)) is None


def test_find_window_for_no_match() -> None:
    windows = [FreeWindow(t(8), t(11))]
    assert find_window_for(windows, t(12), t(13)) is None


def test_format_windows() -> None:
    windows = [FreeWindow(t(9, 20), t(11)), FreeWindow(t(14, 20), t(21))]
    assert format_windows(windows) == "09:20–11:00, 14:20–21:00"


def test_free_window_contains() -> None:
    w = FreeWindow(t(10), t(14))
    assert w.contains(t(10))
    assert w.contains(t(13, 59))
    assert not w.contains(t(14))
    assert not w.contains(t(9, 59))


def test_free_window_covers() -> None:
    w = FreeWindow(t(10), t(14))
    assert w.covers(t(10), t(14))
    assert w.covers(t(11), t(13))
    assert not w.covers(t(9), t(13))
    assert not w.covers(t(11), t(15))
