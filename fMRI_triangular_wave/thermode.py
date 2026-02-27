"""
TCS thermode wrapper with real and simulation modes.
Includes NaN retry on temperature readback.
"""

import math
import time


class ThermodeController:
    """Wrapper around TCS thermode hardware with simulation fallback."""

    def __init__(self, config):
        self.simulation = config['simulation']
        self.baseline_temp = config['baseline_temp']
        self.nan_max_retries = config.get('nan_max_retries', 3)
        self.nan_retry_delay = config.get('nan_retry_delay', 0.01)

        if not self.simulation:
            import TcsControl_python3 as TCS
            self.device = TCS.TcsDevice(port=config['com_port'])
            self.device.set_quiet()
            self.device.set_follow()
            self.device.set_baseline(config['baseline_temp'])
            self.device.set_ramp_speed([config['ramp_rate']] * 5)
            self.device.set_return_speed([config['ramp_rate']] * 5)

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
        """Close thermode connection."""
        if not self.simulation:
            self.device.close()
