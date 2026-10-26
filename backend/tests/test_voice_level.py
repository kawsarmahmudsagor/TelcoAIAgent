import numpy as np
import pytest

from app.agent import voice_level
from app.agent.voice_level import CallerLevel, LoudSpeech


def _tone(amplitude: float, n: int = 480) -> np.ndarray:
    return (np.sign(np.sin(np.arange(n))) * amplitude * 32767).astype(np.int16)


def test_dbfs_of_full_scale_is_zero():
    assert voice_level.dbfs(_tone(1.0)) == pytest.approx(0.0, abs=0.1)


def test_dbfs_of_a_tenth_of_full_scale_is_minus_20():
    assert voice_level.dbfs(_tone(0.1)) == pytest.approx(-20.0, abs=0.1)


def test_dbfs_of_silence_is_the_floor():
    assert voice_level.dbfs(np.zeros(480, dtype=np.int16)) == voice_level.SILENCE_DBFS


def test_uncalibrated_threshold_is_the_fallback():
    level = CallerLevel()
    assert level.reference is None
    assert level.threshold(margin_db=8.0, fallback_dbfs=-35.0) == -35.0


def test_an_accepted_turn_calibrates_the_callers_level():
    level = CallerLevel()
    for db in [-60.0] * 25 + [-22.0] * 75:  # pauses between words, then speech
        level.heard(db)
    level.accept()
    assert level.reference == pytest.approx(-22.0)
    assert level.threshold(margin_db=8.0, fallback_dbfs=-35.0) == pytest.approx(-30.0)


def test_reference_is_the_median_of_recent_turns():
    level = CallerLevel(keep=3)
    for db in (-10.0, -20.0, -30.0, -24.0):
        level.heard(db)
        level.accept()
    # -10 has aged out; median of -20, -30, -24.
    assert level.reference == pytest.approx(-24.0)


def test_a_turn_with_no_speech_frames_does_not_calibrate():
    level = CallerLevel()
    level.accept()
    assert level.reference is None


def test_clear_forgets_frames_heard_before_the_turn():
    level = CallerLevel()
    level.heard(-5.0)
    level.clear()
    level.heard(-25.0)
    level.accept()
    assert level.reference == pytest.approx(-25.0)


def test_accept_starts_a_new_turn():
    level = CallerLevel()
    level.heard(-20.0)
    level.accept()
    level.accept()  # nothing heard since: not a second sample
    level.heard(-40.0)
    level.accept()
    assert level.reference == pytest.approx(-30.0)


def _feed(loud: LoudSpeech, db: float, seconds: float, threshold: float = -30.0) -> bool:
    fired = False
    for _ in range(round(seconds / 0.01)):
        fired = loud.update(db, 0.01, threshold) or fired
    return fired


def test_loud_speech_fires_after_the_minimum_duration():
    loud = LoudSpeech(min_s=0.3)
    assert not _feed(loud, -20.0, 0.25)
    assert _feed(loud, -20.0, 0.06)


def test_quiet_speech_never_fires():
    loud = LoudSpeech(min_s=0.3)
    assert not _feed(loud, -40.0, 3.0)


def test_a_short_dip_between_words_does_not_start_over():
    loud = LoudSpeech(min_s=0.3)
    _feed(loud, -20.0, 0.2)
    _feed(loud, -50.0, 0.1)
    assert _feed(loud, -20.0, 0.16)


def test_a_long_quiet_gap_starts_over():
    loud = LoudSpeech(min_s=0.3)
    _feed(loud, -20.0, 0.2)
    _feed(loud, -50.0, 1.0)
    assert not _feed(loud, -20.0, 0.2)


def test_reset_starts_over():
    loud = LoudSpeech(min_s=0.3)
    _feed(loud, -20.0, 0.25)
    loud.reset()
    assert not _feed(loud, -20.0, 0.1)


def test_current_turn_level():
    level = CallerLevel()
    assert level.current_turn_level() is None
    level.heard(-20.0)
    level.heard(-20.0)
    assert level.current_turn_level() == pytest.approx(-20.0)
    level.clear()
    assert level.current_turn_level() is None

