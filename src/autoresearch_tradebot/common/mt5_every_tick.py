from __future__ import annotations

from functools import lru_cache

MAX_REFERENCE_POINTS = 11
REFERENCE_POINT_DISTRIBUTION: dict[int, tuple[int, int, int]] = {
    3: (1, 1, 1),
    4: (1, 2, 1),
    5: (1, 3, 1),
    6: (1, 4, 1),
    7: (2, 3, 2),
    8: (2, 4, 2),
    9: (2, 5, 2),
    10: (2, 6, 2),
    11: (3, 5, 3),
}


def price_to_ticks(price: float, tick_size: float) -> int:
    return int(round(price / tick_size))


def ticks_to_price(ticks: int, tick_size: float) -> float:
    return float(ticks) * tick_size


def spread_points_to_ticks(spread_points: float, point_size: float, tick_size: float) -> int:
    spread_price = float(spread_points) * point_size
    return max(0, int(round(spread_price / tick_size)))


def candle_bias(open_tick: int, close_tick: int, previous_bias: int) -> int:
    if close_tick > open_tick:
        return 1
    if close_tick < open_tick:
        return -1
    if previous_bias == 1:
        return -1
    if previous_bias == -1:
        return 1
    return 1


def _append_point(path: list[int], value: int) -> None:
    if not path or path[-1] != value:
        path.append(value)


def _allocate_reference_points(
    reference_points: int,
    opening_shadow_size: int,
    closing_shadow_size: int,
) -> tuple[int, int, int]:
    if reference_points <= 0:
        return 0, 0, 0
    if reference_points < 3:
        return 0, reference_points, 0

    opening_shadow_points, range_points, closing_shadow_points = REFERENCE_POINT_DISTRIBUTION[
        reference_points
    ]

    if opening_shadow_size <= 0:
        range_points += opening_shadow_points
        opening_shadow_points = 0
    if closing_shadow_size <= 0:
        range_points += closing_shadow_points
        closing_shadow_points = 0

    if range_points % 2 == 0:
        if opening_shadow_points >= 2 and opening_shadow_size >= closing_shadow_size:
            opening_shadow_points += 1
            range_points -= 1
        elif closing_shadow_points >= 2:
            closing_shadow_points += 1
            range_points -= 1
        elif opening_shadow_points >= 2:
            opening_shadow_points += 1
            range_points -= 1
        else:
            range_points -= 1

    return opening_shadow_points, range_points, closing_shadow_points


def _build_shadow_points(start_tick: int, end_tick: int, count: int) -> list[int]:
    if count <= 0 or start_tick == end_tick:
        return []
    if count == 1:
        return [end_tick]

    distance = abs(start_tick - end_tick)
    direction = 1 if end_tick > start_tick else -1
    points: list[int] = []

    if count == 2:
        midpoint_distance = max(1, distance // 2)
        midpoint = start_tick + (direction * midpoint_distance)
        points.extend([midpoint, end_tick])
        return points

    for index in range(count - 1):
        numerator = count - index - 1
        denominator = count
        offset = max(1, int(round(distance * numerator / denominator)))
        points.append(start_tick + (direction * offset))
    points.append(end_tick)
    return points


def _build_range_points(low_tick: int, high_tick: int, count: int, bias: int) -> list[int]:
    if count <= 0 or low_tick == high_tick:
        return []

    if count == 1:
        return [high_tick if bias == 1 else low_tick]

    waves = (count + 1) // 2
    step = ((high_tick - low_tick - 1) // waves) + 1
    points: list[int] = []

    if bias == 1:
        previous = low_tick
        for wave in range(waves):
            impulse = min(high_tick, previous + step)
            points.append(impulse)
            if wave == waves - 1:
                break
            rollback = min(high_tick, impulse - 1)
            points.append(rollback)
            previous = rollback
        return points

    previous = high_tick
    for wave in range(waves):
        impulse = max(low_tick, previous - step)
        points.append(impulse)
        if wave == waves - 1:
            break
        rollback = max(low_tick, impulse + 1)
        points.append(rollback)
        previous = rollback
    return points


def _build_reference_path(
    high_delta: int,
    low_delta: int,
    close_delta: int,
    reference_points: int,
    bias: int,
) -> tuple[int, ...]:
    open_tick = 0
    high_tick = high_delta
    low_tick = low_delta
    close_tick = close_delta

    if bias == 1:
        opening_shadow_size = max(0, open_tick - low_tick)
        closing_shadow_size = max(0, high_tick - close_tick)
        opening_shadow_end = low_tick
        range_start = low_tick
        range_end = high_tick
        closing_shadow_start = high_tick
        closing_shadow_end = close_tick
    else:
        opening_shadow_size = max(0, high_tick - open_tick)
        closing_shadow_size = max(0, close_tick - low_tick)
        opening_shadow_end = high_tick
        range_start = high_tick
        range_end = low_tick
        closing_shadow_start = low_tick
        closing_shadow_end = close_tick

    opening_shadow_points, range_points, closing_shadow_points = _allocate_reference_points(
        reference_points,
        opening_shadow_size,
        closing_shadow_size,
    )

    path: list[int] = [open_tick]
    for value in _build_shadow_points(open_tick, opening_shadow_end, opening_shadow_points):
        _append_point(path, value)

    low_tick_for_range = min(range_start, range_end)
    high_tick_for_range = max(range_start, range_end)
    for value in _build_range_points(low_tick_for_range, high_tick_for_range, range_points, bias):
        _append_point(path, value)

    for value in _build_shadow_points(closing_shadow_start, closing_shadow_end, closing_shadow_points):
        _append_point(path, value)

    if path[-1] != close_tick:
        _append_point(path, close_tick)
    return tuple(path)


@lru_cache(maxsize=200_000)
def generate_every_tick_path(
    high_delta: int,
    low_delta: int,
    close_delta: int,
    tick_volume: int,
    previous_bias: int,
) -> tuple[int, ...]:
    if tick_volume <= 1:
        return (close_delta,)
    if tick_volume == 2:
        return (0, close_delta)

    bias = candle_bias(0, close_delta, previous_bias)
    reference_points = max(3, min(int(tick_volume), MAX_REFERENCE_POINTS))
    reference_path = _build_reference_path(
        high_delta=high_delta,
        low_delta=low_delta,
        close_delta=close_delta,
        reference_points=reference_points,
        bias=bias,
    )

    if len(reference_path) <= 1:
        return reference_path

    total_distance = 0
    for left, right in zip(reference_path, reference_path[1:]):
        total_distance += abs(right - left)
    saw_enabled = int(tick_volume) > max(1, total_distance)

    low_bound = low_delta
    high_bound = high_delta
    path: list[int] = [reference_path[0]]

    for start_tick, end_tick in zip(reference_path, reference_path[1:]):
        if start_tick == end_tick:
            continue

        direction = 1 if end_tick > start_tick else -1
        current = start_tick
        while current != end_tick:
            next_tick = current + direction
            if saw_enabled:
                bounce_tick = current - direction
                if low_bound <= bounce_tick <= high_bound:
                    _append_point(path, bounce_tick)
            _append_point(path, next_tick)
            current = next_tick

    if path[-1] != close_delta:
        _append_point(path, close_delta)
    return tuple(path)
