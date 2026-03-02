"""
Configuration for fMRI tprf thermode experiment.
All configurable parameters in one place.
"""

CONFIG = {
    # Thermal
    'baseline_temp': 30.0,       # degrees C
    'temp_min': 10.0,            # degrees C (safety clamp lower bound)
    'temp_max': 50.0,            # degrees C (safety clamp upper bound)
    'max_delta': 17.5,           # degrees C amplitude
    'ramp_rate': 50.0,           # degrees C/s (TCS hardware ramp speed in follow mode)
                                 # Must be >> waveform rate (~0.9 C/s) so the hardware
                                 # can reach each 10Hz micro-step within 100ms.
                                 # 50 C/s accounts for the MRI filter on the TCS cable.
                                 # Each 0.09 C step takes ~1.8ms at 50 C/s (98ms margin).
    'cycle_duration': 80.0,      # seconds per full triangle cycle
    'cycles_per_block': 8.5,        # 8 full + 1 half = 8 full sweeps each direction
    'baseline_buffer': 30.0,     # seconds of baseline before/after block

    # Update rate
    'update_hz': 10,             # thermode update frequency

    # MR
    'trigger_key': 't',          # scanner trigger key
    'TR': 1.5,                   # seconds
    'dummy_volumes': 4,
    'emulate': False,            # True = use space instead of trigger

    # Mask selection (one per condition; counterbalanced across participants)
    'nontgi_mask': 'P1_W',      # which NonTGI mask to use for this participant
    'tgi_mask': 'TGI_1',        # which TGI mask to use for this participant

    # Block order counterbalancing
    # True  = Group A: NonTGI warm-first, NonTGI cool-first, TGI warm, TGI cool
    # False = Group B: NonTGI cool-first, NonTGI warm-first, TGI warm, TGI cool
    'nontgi_warm_first': True,

    # Thermode
    'com_port': 'COM3',          # serial port
    'simulation': False,         # True = no thermode commands

    # VAS ratings
    'vas_enabled': False,            # disabled for pilot
    'vas_max_duration': 8.0,         # seconds per question
    'vas_labels': ['Not at all', 'Extremely'],

    # Display
    'fullscreen': True,          # True for scanner
    'screen_index': 1,           # 0 = primary, 1 = extended display
}
