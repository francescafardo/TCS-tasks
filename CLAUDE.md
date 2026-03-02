# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

fMRI thermal population receptive field (tpRF) experiment. Delivers continuous triangular-wave thermal stimulation via a 5-zone TCS thermode during fMRI scanning. Compares Thermal Grill Illusion (TGI) and Non-TGI spatial temperature patterns. Built with Python 3.8+ and PsychoPy.

## Running the Experiment

All code lives in `fMRI_triangular_wave/`. There is no build step, test suite, or linter.

```bash
cd fMRI_triangular_wave

# Run one block (main entry point — run once per block, 4 blocks per session)
python run_experiment.py

# Live QC dashboard (separate terminal, while experiment runs)
python qc_monitor.py

# Generate GLM/pRF design matrices (post-processing)
python generate_design_matrix.py --sub 0001 --ses 01
```

Default config (`config.py`) has `simulation = True` and `emulate = True` — no hardware needed. Press **space** to simulate scanner trigger.

## Architecture

**Execution flow:** `run_experiment.py` → GUI dialogs → init thermode → wait for scanner trigger → `run_block.py` (10 Hz control loop) → VAS ratings → save BIDS output.

Key modules and their roles:
- **config.py** — Single `CONFIG` dict with all parameters (thermal, timing, scanner, masks, hardware, display)
- **run_experiment.py** — Main entry point: two-step GUI, block plan management, trigger wait, orchestrates block + ratings + file saving
- **run_block.py** — Real-time 10 Hz loop: applies waveform to thermode zones, logs thermode data (TSV), tracks QC per cycle
- **waveform.py** — Pure numpy functions: `generate_delta_waveform()`, `phase_shift_waveform()`, `apply_mask()`
- **masks.py** — Static dict of 6 spatial masks defining zone polarity (+1 warm, -1 cool, 0 neutral)
- **thermode.py** — `ThermodeController` class wrapping TCS II.1 hardware with simulation fallback
- **qc.py** — `ThermalQC` class: accumulates per-sample metrics, produces per-cycle summaries (ramp rate, temp error, flags)
- **qc_monitor.py** — Standalone matplotlib dashboard: polls thermode TSV every 2s, plots zone temps + error
- **ratings.py** — `collect_vas_ratings()`: post-block VAS scales using pyglet keyboard handler (8s timeout)
- **generate_design_matrix.py** — Standalone CLI: GLM regressors with HRF convolution, pRF apertures, outputs TSV/NPZ/MAT/PNG

**Module dependency graph:**
```
config → waveform → run_block → run_experiment
         masks ──────────────→ run_experiment
         thermode ──→ run_block, run_experiment
         qc ────────→ run_block
         ratings ──────────────→ run_experiment
```

## Key Design Constraints

- **Real-time control loop** in `run_block.py` runs at 10 Hz. Changes here must preserve timing precision.
- **Temperature safety**: all zone temperatures are clamped to `temp_min`–`temp_max` (10–50 C) in `waveform.apply_mask()`.
- **One invocation per block**: the script exits after each block. Block completion is tracked by scanning for existing output files.
- **Data is never overwritten**: each output file includes a timestamp. Re-running a block creates new files.
- **Hardware abstraction**: `ThermodeController` handles both real TCS device and simulated mode via the same interface.

## Output Format

BIDS-compatible files in `data/sub-{ID}/ses-{session}/func/`:
- `_events_<timestamp>.tsv` — block phases + VAS ratings
- `_thermode_<timestamp>.tsv` — 10 Hz thermode recording (no header; see JSON sidecar)
- `_thermode_<timestamp>.json` — column definitions + experiment parameters
- `_qc_<timestamp>.tsv` — per-cycle QC metrics

## Dependencies

- PsychoPy (with pyglet backend), NumPy, matplotlib, scipy
- `TcsControl_python3` — only needed when `simulation = False`
- No requirements.txt or virtual environment setup exists
