"""
Spatial mask definitions for TGI and Non-TGI conditions.

Each participant receives one NonTGI mask and one TGI mask.
Each mask is presented for an entire block (8 cycles) with the same
waveform, run twice per condition (warm-first + cool-first) for pRF
phase-encoding analysis.

Mask selection is counterbalanced across participants via config.
"""

# Non-TGI masks: 2 positions x 2 polarities (4-bar thermode, zones 1-4)
# P1 = zones 1,2 (proximal)  P3 = zones 3,4 (distal)
NONTGI_MASKS = {
    'P1_W': [+1, +1,  0,  0,  0],
    'P1_C': [-1, -1,  0,  0,  0],
    'P3_W': [ 0,  0, +1, +1,  0],
    'P3_C': [ 0,  0, -1, -1,  0]
}

# TGI masks: alternating warm/cool patterns
TGI_MASKS = {
    'TGI_1': [+1, -1, +1, -1,  0],
    'TGI_2': [-1, +1, -1, +1,  0]
}

# Combined lookup for convenience
ALL_MASKS = {**NONTGI_MASKS, **TGI_MASKS}


def get_mask(name):
    """Look up a mask by name.

    Returns
    -------
    list of int
        5-element mask array.

    Raises
    ------
    KeyError
        If mask name is not found.
    """
    return ALL_MASKS[name]
