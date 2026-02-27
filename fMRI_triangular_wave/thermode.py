"""
TCS II.1 thermode wrapper with real and simulation modes.

Uses follow mode: the experiment sends target temperatures at 10 Hz and the
TCS hardware ramps toward each target at the configured ramp speed.  The ramp
speed must be high (e.g. 100 deg/s) so the hardware reaches each small
micro-step (~0.09 deg) well within the 100 ms update interval.  The smooth
waveform shape is determined by the software update sequence, not the hardware
ramp rate.

Initialization sequence (matches phs_lifespan MATLAB reference):
    1. set_quiet        – suppress auto temperature display
    2. set_baseline     – neutral temperature for all zones
    3. set_durations    – max duration to prevent safety-timer cutoff
    4. set_ramp_speed   – fast tracking for follow mode
    5. set_return_speed – fast tracking for follow mode
    6. set_temperatures – initial baseline targets
    7. set_follow       – enter follow mode (probe ramps to target)

Cleanup:
    abort_stimulation → set_baseline → close
"""

import math
import time


class ThermodeController:
    """Wrapper around TCS II.1 thermode hardware with simulation fallback."""

    # Maximum duration the TCS accepts (ms). Setting this high prevents the
    # safety time/temperature function from cutting off long stimulation
    # blocks.  Manual §2.1.2 warns about automatic cutoff at high temps.
    MAX_DURATION_S = 99.999  # 99999 ms

    def __init__(self, config):
        self.simulation = config['simulation']
        self.baseline_temp = config['baseline_temp']
        self.nan_max_retries = config.get('nan_max_retries', 3)
        self.nan_retry_delay = config.get('nan_retry_delay', 0.01)

        if not self.simulation:
            import TcsControl_python3 as TCS
            self.device = TCS.TcsDevice(port=config['com_port'])
            self.device.set_quiet()
            self.device.set_baseline(config['baseline_temp'])
            self.device.set_durations([self.MAX_DURATION_S] * 5)
            self.device.set_ramp_speed([config['ramp_rate']] * 5)
            self.device.set_return_speed([config['ramp_rate']] * 5)
            self.device.set_temperatures([config['baseline_temp']] * 5)
            self.device.set_follow()

    def set_temperatures(self, temps):
        """Send target temperatures to 5 zones.

        Parameters
        ----------
        temps : list of float
            5 temperature values in degrees C.
        """
        if not self.simulation:
            self.device.set_temperatures(temps)

    def get_temperatures(self):
        """Read actual temperatures from 5 zones with NaN retry.

        Retries up to nan_max_retries times if the device returns NaN values.

        Returns
        -------
        list of float
            5 temperature readings. Returns NaN in simulation mode.
        """
        if self.simulation:
            return [math.nan] * 5

        for attempt in range(self.nan_max_retries):
            temps = self.device.get_temperatures()
            if temps is not None and not any(
                t != t for t in temps if isinstance(t, float)
            ):
                return temps
            if attempt < self.nan_max_retries - 1:
                time.sleep(self.nan_retry_delay)

        # Return whatever we got on the last attempt
        return temps if temps is not None else [math.nan] * 5

    def set_baseline(self):
        """Set all zones to baseline temperature."""
        baseline = [self.baseline_temp] * 5
        self.set_temperatures(baseline)

    def close(self):
        """Abort stimulation, return to baseline, and close connection."""
        if not self.simulation:
            try:
                self.device.abort_stimulation()
            except (AttributeError, Exception):
                pass  # abort_stimulation may not exist in all library versions
            self.set_baseline()
            self.device.close()
