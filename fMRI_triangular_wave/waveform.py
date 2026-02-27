"""
Triangle waveform generation and mask application for thermal stimulation.
"""

import numpy as np


def generate_delta_waveform(cycle_duration, update_hz, max_delta=20.0):
    """Generate one full cycle of a triangle wave as delta values.

    The waveform rises linearly 0 -> max_delta over quarter-cycle, falls back
    to 0, rises again, falls again, completing two full triangle periods within
    one cycle_duration.

    Parameters
    ----------
    cycle_duration : float
        Total duration of one cycle in seconds (default 80s).
    update_hz : int
        Samples per second (default 10).
    max_delta : float
        Peak amplitude in degrees C (default 20).

    Returns
    -------
    np.ndarray
        1-D array of delta values, length = cycle_duration * update_hz.
    """
    n_samples = int(cycle_duration * update_hz)
    period = cycle_duration / 2.0  # 40s per triangle period
    t = np.arange(n_samples) / update_hz  # time in seconds

    # Standard triangle wave: period=40s, amplitude=max_delta
    delta = max_delta * (1.0 - np.abs(2.0 * (t % period) / period - 1.0))
    return delta


def phase_shift_waveform(waveform):
    """Shift waveform by half-period for cool-first blocks.

    The triangle wave has period = cycle_duration / 2. Shifting by half a
    period (= quarter cycle = len//4 samples) moves the waveform so that
    delta starts at max_delta and decreases, making warm zones cool first.
    """
    return np.roll(waveform, len(waveform) // 4)


def apply_mask(delta, mask, baseline_temp=30.0, temp_min=10.0, temp_max=50.0):
    """Compute 5-zone temperatures from a scalar delta and mask.

    Parameters
    ----------
    delta : float
        Current delta value from the waveform.
    mask : list or np.ndarray
        5-element array with values +1 (warm), -1 (cool), or 0 (neutral).
    baseline_temp : float
        Baseline temperature in degrees C.
    temp_min, temp_max : float
        Safety clamp bounds.

    Returns
    -------
    list of float
        5 zone temperatures, clamped to [temp_min, temp_max].
    """
    temps = []
    for s in mask:
        t = baseline_temp + s * delta
        t = max(temp_min, min(temp_max, t))
        temps.append(round(t, 2))
    return temps
