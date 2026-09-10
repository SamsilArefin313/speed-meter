"""Per-track speed measurement using two virtual timing gates."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Measurement:
    speed_kph: float = 0.0
    elapsed_seconds: float | None = None
    timing: bool = False
    direction: str | None = None
    completed: bool = False


@dataclass
class TrackState:
    x: float
    timestamp: float
    last_seen: float
    start_line: str | None = None
    start_time: float | None = None
    speed_kph: float = 0.0
    elapsed_seconds: float | None = None
    direction: str | None = None


class SpeedEstimator:
    """Time a tracked center point between vertical lines A and B."""

    def __init__(self, distance_meters: float = 10.0):
        self.distance_meters = distance_meters
        self._tracks: dict[int, TrackState] = {}

    @staticmethod
    def _crossing_fraction(previous_x: float, x: float, line_x: float) -> float | None:
        if previous_x == x:
            return None
        fraction = (line_x - previous_x) / (x - previous_x)
        return fraction if 0.0 < fraction <= 1.0 else None

    def update(self, track_id: int, center_x: float, line_a_x: float,
               line_b_x: float, timestamp: float | None = None) -> Measurement:
        now = monotonic() if timestamp is None else timestamp
        previous = self._tracks.get(track_id)
        if previous is None:
            self._tracks[track_id] = TrackState(center_x, now, now)
            return Measurement()

        dt = now - previous.timestamp
        completed = False
        crossings: list[tuple[float, str]] = []
        if 0.0 < dt <= 10.0:
            for name, position in (("A", line_a_x), ("B", line_b_x)):
                fraction = self._crossing_fraction(previous.x, center_x, position)
                if fraction is not None:
                    crossings.append((fraction, name))

        for fraction, line_name in sorted(crossings):
            crossing_time = previous.timestamp + fraction * dt
            if previous.start_line is None:
                previous.start_line = line_name
                previous.start_time = crossing_time
            elif line_name != previous.start_line and previous.start_time is not None:
                direction = f"{previous.start_line} -> {line_name}"
                elapsed = crossing_time - previous.start_time
                if elapsed > 0.0:
                    speed = self.distance_meters / elapsed * 3.6
                    if speed <= 300.0:
                        previous.speed_kph = speed
                        previous.elapsed_seconds = elapsed
                        previous.direction = direction
                        completed = True
                previous.start_line = None
                previous.start_time = None

        previous.x = center_x
        previous.timestamp = now
        previous.last_seen = now
        return Measurement(
            previous.speed_kph,
            previous.elapsed_seconds,
            previous.start_line is not None,
            previous.direction,
            completed,
        )

    def prune(self, timestamp: float | None = None, max_age: float = 3.0) -> None:
        now = monotonic() if timestamp is None else timestamp
        self._tracks = {key: value for key, value in self._tracks.items()
                        if now - value.last_seen <= max_age}
