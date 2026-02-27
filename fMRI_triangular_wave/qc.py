"""
Real-time quality control for thermode temperature delivery.

Tracks per-sample and per-cycle metrics:
- Actual ramp rate vs expected (flags deviations from 1 deg/s)
- Onset latency: delay between commanded and actual temp change
- Commanded vs actual temperature error
- Warming vs cooling ramp rate asymmetry
"""

import math
import numpy as np


class ThermalQC:
    """Accumulates per-sample thermode data and computes QC metrics.

    Usage:
        qc = ThermalQC(config)
        qc.start_cycle(cycle_idx)
        for each sample:
            qc.update(timestamp, commanded, actual, delta, mask)
        summary = qc.end_cycle()
    """

    # Threshold for flagging ramp rate deviations (deg/s)
    RAMP_RATE_TOLERANCE = 0.3
    # Threshold for detecting onset (actual deviates from baseline, deg C)
    ONSET_THRESHOLD = 0.5
    # Threshold for flagging large temperature errors (deg C)
    TEMP_ERROR_THRESHOLD = 2.0

    def __init__(self, config):
        self.update_hz = config['update_hz']
        self.baseline_temp = config['baseline_temp']
        self.expected_ramp_rate = config['ramp_rate']  # 1.0 deg/s
        self.simulation = config['simulation']

        self._cycle_summaries = []
        self._reset_cycle()

    def _reset_cycle(self):
        """Reset accumulators for a new cycle."""
        self._cycle_idx = None
        self._prev_actual = None
        self._prev_timestamp = None
        self._onset_detected = False
        self._onset_latency = math.nan
        self._command_change_time = None

        # Per-sample accumulators
        self._ramp_rates = []        # actual ramp rate at each sample
        self._temp_errors = []       # |commanded - actual| per active zone
        self._warming_rates = []     # ramp rates during warming phase
        self._cooling_rates = []     # ramp rates during cooling phase
        self._deltas = []            # delta values for phase detection
        self._n_ramp_flags = 0       # number of samples with bad ramp rate

    def start_cycle(self, cycle_idx):
        """Begin tracking a new cycle."""
        self._reset_cycle()
        self._cycle_idx = cycle_idx

    def update(self, timestamp, commanded, actual, delta, mask):
        """Process one sample.

        Parameters
        ----------
        timestamp : float
            Time from trigger (seconds).
        commanded : list of float
            5-zone commanded temperatures.
        actual : list of float
            5-zone actual temperatures from thermode.
        delta : float
            Current waveform delta value.
        mask : list of int
            5-zone mask array (+1, -1, or 0).
        """
        if self.simulation:
            return

        # Identify active zones
        active_zones = [i for i, m in enumerate(mask) if m != 0]
        if not active_zones:
            return

        # --- Temperature error (commanded vs actual) ---
        for z in active_zones:
            c = commanded[z]
            a = actual[z]
            if not (math.isnan(a) or math.isnan(c)):
                error = abs(c - a)
                self._temp_errors.append(error)
                if error > self.TEMP_ERROR_THRESHOLD:
                    print(f'  QC WARNING: zone {z+1} temp error = '
                          f'{error:.1f} C (commanded={c:.1f}, actual={a:.1f})')

        # --- Onset detection ---
        if not self._onset_detected and delta > 0 and self._command_change_time is None:
            self._command_change_time = timestamp

        if not self._onset_detected:
            for z in active_zones:
                a = actual[z]
                if not math.isnan(a):
                    if abs(a - self.baseline_temp) > self.ONSET_THRESHOLD:
                        self._onset_detected = True
                        if self._command_change_time is not None:
                            self._onset_latency = timestamp - self._command_change_time
                        break

        # --- Ramp rate from consecutive actual readings ---
        if self._prev_actual is not None and self._prev_timestamp is not None:
            dt = timestamp - self._prev_timestamp
            if dt > 0:
                rates = []
                for z in active_zones:
                    a_now = actual[z]
                    a_prev = self._prev_actual[z]
                    if not (math.isnan(a_now) or math.isnan(a_prev)):
                        rate = abs(a_now - a_prev) / dt
                        rates.append(rate)

                if rates:
                    mean_rate = sum(rates) / len(rates)
                    self._ramp_rates.append(mean_rate)

                    # Classify as warming or cooling phase
                    self._deltas.append(delta)
                    prev_delta = self._deltas[-2] if len(self._deltas) >= 2 else delta
                    if delta > prev_delta:
                        self._warming_rates.append(mean_rate)
                    elif delta < prev_delta:
                        self._cooling_rates.append(mean_rate)

                    # Flag if ramping but rate is wrong
                    if mean_rate > 0.05:  # only flag when actually ramping
                        if abs(mean_rate - self.expected_ramp_rate) > self.RAMP_RATE_TOLERANCE:
                            self._n_ramp_flags += 1
                            if self._n_ramp_flags <= 3:  # limit console spam
                                print(f'  QC WARNING: ramp rate = {mean_rate:.2f} '
                                      f'deg/s (expected {self.expected_ramp_rate:.1f} '
                                      f'+/- {self.RAMP_RATE_TOLERANCE})')

        self._prev_actual = list(actual)
        self._prev_timestamp = timestamp

    def end_cycle(self):
        """Finalise cycle and return summary dict."""
        ramp_rates = np.array(self._ramp_rates) if self._ramp_rates else np.array([])
        warming = np.array(self._warming_rates) if self._warming_rates else np.array([])
        cooling = np.array(self._cooling_rates) if self._cooling_rates else np.array([])
        errors = np.array(self._temp_errors) if self._temp_errors else np.array([])

        # Filter ramp rates to only active ramping samples (rate > 0.05 deg/s)
        active_ramp = ramp_rates[ramp_rates > 0.05] if len(ramp_rates) > 0 else np.array([])
        active_warming = warming[warming > 0.05] if len(warming) > 0 else np.array([])
        active_cooling = cooling[cooling > 0.05] if len(cooling) > 0 else np.array([])

        summary = {
            'cycle_index': self._cycle_idx,
            'onset_latency_s': self._onset_latency,
            'mean_ramp_rate': _safe_mean(active_ramp),
            'std_ramp_rate': _safe_std(active_ramp),
            'mean_warming_rate': _safe_mean(active_warming),
            'mean_cooling_rate': _safe_mean(active_cooling),
            'warming_cooling_diff': (
                _safe_mean(active_warming) - _safe_mean(active_cooling)
            ),
            'mean_temp_error': _safe_mean(errors),
            'max_temp_error': _safe_max(errors),
            'n_ramp_flags': self._n_ramp_flags,
            'n_samples': len(ramp_rates),
        }

        self._cycle_summaries.append(summary)
        return summary

    def get_block_summaries(self):
        """Return list of all cycle summaries for the block."""
        return list(self._cycle_summaries)

    def reset_block(self):
        """Clear all cycle summaries for a new block."""
        self._cycle_summaries = []
        self._reset_cycle()


def _safe_mean(arr):
    return float(np.nanmean(arr)) if len(arr) > 0 else math.nan


def _safe_std(arr):
    return float(np.nanstd(arr)) if len(arr) > 0 else math.nan


def _safe_max(arr):
    return float(np.nanmax(arr)) if len(arr) > 0 else math.nan
