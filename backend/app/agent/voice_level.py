"""How loud the mic is, to tell the customer from the room.

The customer sits closest to the mic, so their voice arrives louder than other
people talking, a TV, or what's left of the agent's own voice after echo
cancellation. Mic levels differ by 20 dB between a headset and a laptop, so the
bar is set per call: the customer's level is learned from the turns the gate
accepts (CallerLevel), and speech over the agent counts as the customer only
when it comes within a margin of that level for long enough (LoudSpeech).

Pure functions and small state machines, no livekit imports; the wiring is in
app.agent.gated_agent. The browser publishes the mic with automatic gain control
off, which would otherwise turn quiet rooms up and close the gap.
"""

import statistics
from collections import deque

import numpy as np

# Digital silence; also the floor so log10 never sees 0.
SILENCE_DBFS = -100.0
# Speech frames quieter than this say nothing about the customer's level.
_SPEECH_FLOOR_DBFS = -70.0
# The loud end of a turn: its quieter frames are the gaps between words.
_TURN_PERCENTILE = 75


def dbfs(samples: np.ndarray) -> float:
    """RMS level of int16 samples, in dB below full scale."""
    if samples.size == 0:
        return SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64))))) / 32768.0
    if rms <= 0.0:
        return SILENCE_DBFS
    return max(SILENCE_DBFS, 20.0 * float(np.log10(rms)))


class CallerLevel:
    """The customer's speaking level: the median over their last `keep`
    accepted turns, each measured at its loud end."""

    def __init__(self, keep: int = 5) -> None:
        self._turns: deque[float] = deque(maxlen=keep)
        self._frames: list[float] = []

    def heard(self, db: float) -> None:
        """A frame of user speech while the agent listens."""
        if db >= _SPEECH_FLOOR_DBFS:
            self._frames.append(db)

    def clear(self) -> None:
        """Forgets frames heard so far: a new turn starts."""
        self._frames.clear()

    def accept(self) -> None:
        """The frames heard since clear() were the customer's turn."""
        if self._frames:
            self._turns.append(float(np.percentile(self._frames, _TURN_PERCENTILE)))
        self._frames.clear()

    @property
    def reference(self) -> float | None:
        return statistics.median(self._turns) if self._turns else None

    def threshold(self, *, margin_db: float, fallback_dbfs: float) -> float:
        ref = self.reference
        return fallback_dbfs if ref is None else ref - margin_db


class LoudSpeech:
    """Fires once speech has been at or above the threshold for `min_s`. A quiet
    frame takes back half its length, so a dip between words doesn't start over
    but a real pause does."""

    def __init__(self, min_s: float) -> None:
        self.min_s = min_s
        self._loud_s = 0.0

    def update(self, db: float, duration_s: float, threshold: float) -> bool:
        if db >= threshold:
            self._loud_s += duration_s
        else:
            self._loud_s = max(0.0, self._loud_s - duration_s / 2)
        return self._loud_s >= self.min_s

    def reset(self) -> None:
        self._loud_s = 0.0
