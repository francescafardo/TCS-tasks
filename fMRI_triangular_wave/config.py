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
    'ramp_rate': 1.0,            # degrees C/s (hardware ramp speed)
    'cycle_duration': 80.0,      # seconds per full triangle cycle
    'cycles_per_block': 8,
    'baseline_buffer': 30.0,     # seconds of baseline before/after block

    # Update rate
    'update_hz': 10,             # thermode update frequency

    # MR
    'trigger_key': '5',          # scanner trigger key
    'TR': 1.5,                   # seconds
    'dummy_volumes': 4,
    'emulate': True,             # True = use space instead of trigger

    # Mask selection (one per condition; counterbalanced across participants)
    'nontgi_mask': 'P1_W',      # which NonTGI mask to use for this participant
    'tgi_mask': 'TGI_1',        # which TGI mask to use for this participant

    # Block order counterbalancing
    # True  = Group A: NonTGI warm-first, NonTGI cool-first, TGI warm, TGI cool
    # False = Group B: NonTGI cool-first, NonTGI warm-first, TGI warm, TGI cool
    'nontgi_warm_first': True,

    # Thermode
    'com_port': 'COM6',          # serial port
    'simulation': True,          # True = no thermode commands

    # VAS ratings
    'vas_enabled': False,            # disabled for pilot
    'vas_max_duration': 8.0,         # seconds per question
    'vas_labels': ['Not at all', 'Extremely'],

    # Display
    'fullscreen': False,         # True for scanner
    'screen_index': 0,
}
