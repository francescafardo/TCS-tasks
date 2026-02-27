# fMRI Thermal pRF (tprf) Experiment

Continuous triangular-wave thermal stimulation delivered via a 5-zone TCS thermode during fMRI scanning. Designed for thermal population receptive field (pRF) mapping, comparing **TGI** (Thermal Grill Illusion) and **Non-TGI** spatial patterns.

Built with **PsychoPy** (Python). Each block is run as an independent invocation of the script, giving the experimenter full control over inter-block timing.

## Requirements

- Python 3.8+
- [PsychoPy](https://www.psychopy.org/) (with pyglet backend)
- NumPy
- `TcsControl_python3` module (only needed when `simulation = False`)

## Quick Start (Simulation Mode)

```bash
python run_experiment.py
```

Default settings in `config.py` have `simulation = True` and `emulate = True`, so no thermode hardware or scanner trigger is needed. Press **space** to start after the trigger prompt.

## Experimental Design

### Overview

Each session consists of **4 blocks**, run one at a time:

| Block | Condition | Sweep direction |
|-------|-----------|-----------------|
| 1     | NonTGI    | warm-first *or* cool-first |
| 2     | NonTGI    | cool-first *or* warm-first |
| 3     | TGI       | warm-first |
| 4     | TGI       | cool-first |

The NonTGI block order (warm-first vs cool-first first) is counterbalanced across participants via the `nontgi_warm_first` config flag.

### Block Structure

```
[30s baseline] → [8 x 80s stimulation cycles] → [30s baseline] → [VAS ratings]
```

- **Baseline**: all 5 zones held at 30 C
- **Stimulation**: triangular waveform with 1 C/s ramp rate, 20 C amplitude (temperature range: 10-50 C)
- **VAS ratings**: 3 questions (cold, warm, burning intensity) with 8s timeout each

### Triangular Waveform

Each 80s cycle contains **two full triangle periods** (40s each):

```
delta        /\              /\
(C)         /  \            /  \
 20        /    \          /    \
          /      \        /      \
         /        \      /        \
  0   --/          \    /          \--
                    \  /
                     \/
        |-- 40s period --|-- 40s period --|
        |------------ 80s cycle ----------|
```

- **Warm-first**: delta starts at 0 and rises (warm zones heat up first)
- **Cool-first**: delta starts at 20 and falls (warm zones cool down first). Both directions are needed within-subject to cancel HRF delay in pRF analysis.

### Spatial Masks

Each mask defines how the 5 thermode zones respond to the delta waveform:
- `+1` = warm zone: `T = baseline + delta`
- `-1` = cool zone: `T = baseline - delta`
- ` 0` = neutral zone: `T = baseline`

**Non-TGI masks** (uniform polarity, 2 adjacent zones):

| Mask   | Z1  | Z2  | Z3  | Z4  | Z5  | Description |
|--------|-----|-----|-----|-----|-----|-------------|
| P1_W   | +1  | +1  |  0  |  0  |  0  | Proximal warm |
| P1_C   | -1  | -1  |  0  |  0  |  0  | Proximal cool |
| P3_W   |  0  |  0  | +1  | +1  |  0  | Distal warm |
| P3_C   |  0  |  0  | -1  | -1  |  0  | Distal cool |

**TGI masks** (alternating warm/cool):

| Mask   | Z1  | Z2  | Z3  | Z4  | Z5  | Description |
|--------|-----|-----|-----|-----|-----|-------------|
| TGI_1  | +1  | -1  | +1  | -1  |  0  | W-C alternating |
| TGI_2  | -1  | +1  | -1  | +1  |  0  | C-W alternating |

Each participant is assigned **one NonTGI mask** and **one TGI mask** (set in config), counterbalanced across participants.

## Running the Experiment

### Step-by-Step

1. **Edit `config.py`** before the session to set participant-specific parameters:
   - `nontgi_mask`: which NonTGI mask (e.g. `'P1_W'`, `'P3_C'`)
   - `tgi_mask`: which TGI mask (e.g. `'TGI_1'`, `'TGI_2'`)
   - `nontgi_warm_first`: `True` (Group A) or `False` (Group B)
   - `com_port`: serial port for the TCS thermode
   - `simulation`: set to `False` for real thermode control

2. **Run the script**:
   ```bash
   python run_experiment.py
   ```

3. **Dialog 1 — Participant Info**: enter participant ID (e.g. `0001`) and session number (e.g. `01`).

4. **Dialog 2 — Block Selection**: the GUI displays a block plan summary showing which blocks have been completed:
   ```
   --- Block Plan ---
     Block 1 (run-01): NonTGI  P1_W  W-first  [DONE]
     Block 2 (run-02): NonTGI  P1_W  C-first  [--]
     Block 3 (run-03): TGI  TGI_1  W-first  [--]
     Block 4 (run-04): TGI  TGI_1  C-first  [--]
   ```
   Select the block to run (defaults to the next pending block). Block type, mask, and sweep direction are auto-populated from the plan. Also confirm hardware settings (COM port, simulation mode, emulate scanner, fullscreen).

5. **Scanner trigger**: the PsychoPy window shows "Waiting for scanner trigger...". In emulation mode, press **space**. In scanner mode, the script waits for the configured trigger key (`5` by default). After the trigger, it waits for dummy volumes (default: 4 x 1.5s = 6s).

6. **Stimulation runs** with a fixation circle at screen centre. Experimenter status is shown at the bottom of the screen. Press **Escape** to abort.

7. **VAS ratings** (if enabled): 3 questions presented sequentially. Use **left/right arrows** to move the cursor, **up arrow** to confirm. 8s timeout per question.

8. **Block complete**: data is saved and the script exits. Run the script again for the next block.

### Between Blocks

Take as much time as needed between blocks. The script is designed to be invoked once per block — simply run `python run_experiment.py` again when ready. The block plan summary will show which blocks are already done.

### Re-running a Block

If you need to re-run a completed block, select it from the dropdown. A warning will be printed but the run will proceed. Data is saved with a unique timestamp, so previous data is never overwritten.

## Output Files

All output is saved under `data/sub-{ID}/ses-{session}/func/` in BIDS-compatible format. Each block produces 4 files:

### `_events_<timestamp>.tsv`

BIDS events file with block phase timings and VAS ratings.

| Column | Description |
|--------|-------------|
| onset | Seconds from scanner trigger |
| duration | Event duration in seconds |
| trial_type | `baseline`, `stimulation`, or `rating_{question}` |
| block_type | `NonTGI` or `TGI` |
| mask_name | Mask used (e.g. `P1_W`, `TGI_1`) |
| warm_first | `1` (warm-first) or `0` (cool-first) |
| response_value | VAS rating (0-100) or `n/a` |
| response_time | Reaction time in seconds or `n/a` |

### `_thermode_<timestamp>.tsv`

10 Hz thermode recording (no header; columns defined in the JSON sidecar).

Columns: `onset`, `volume`, `block_index`, `block_type`, `cycle_index`, `mask_name`, `warm_first`, `delta`, `zone1_set` ... `zone5_set`, `zone1_actual` ... `zone5_actual`

### `_thermode_<timestamp>.json`

JSON sidecar for the thermode TSV. Contains column definitions and all experiment parameters (sampling frequency, temperatures, timing, mask, etc.).

### `_qc_<timestamp>.tsv`

Per-cycle quality control metrics.

| Column | Description |
|--------|-------------|
| onset_latency_s | Delay between commanded and actual temperature change |
| mean_ramp_rate | Mean actual ramp rate (target: 1.0 C/s) |
| std_ramp_rate | Ramp rate variability |
| mean_warming_rate | Mean ramp rate during warming phases |
| mean_cooling_rate | Mean ramp rate during cooling phases |
| warming_cooling_diff | Asymmetry between warming and cooling rates |
| mean_temp_error | Mean absolute error between commanded and actual temps |
| max_temp_error | Maximum temperature error in the cycle |
| n_ramp_flags | Number of samples where ramp rate deviated > 0.3 C/s from target |
| n_samples | Total samples in the cycle |

## Real-Time QC Monitor

A live matplotlib dashboard for monitoring thermode performance during the experiment. Run it in a **second terminal** while the experiment is running.

### Usage

```bash
# Auto-detect the latest thermode file in data/
python qc_monitor.py

# Or specify a file explicitly
python qc_monitor.py data/sub-0001/ses-01/func/sub-0001_ses-01_task-tprf_run-01_thermode_20260227T140000.tsv
```

### Dashboard Panels

1. **Delta waveform** — commanded temperature modulation over time, with sample count
2. **Zone temperatures** — commanded (solid) vs actual (dashed) for each active zone, with baseline reference line
3. **Temperature error** — |commanded - actual| per active zone, with 2°C warning threshold

The dashboard updates every 2 seconds by re-reading the TSV file. Thermode data is flushed to disk every ~1 second (every 10 samples at 10 Hz) so the monitor stays current.

### Requirements

- matplotlib (included with PsychoPy)
- numpy

## File Structure

```
fMRI_triangular_wave/
  config.py          — All configurable parameters
  waveform.py        — Triangle wave generation + phase shifting + mask application
  masks.py           — Spatial mask definitions (NonTGI and TGI)
  thermode.py        — TCS thermode hardware wrapper (real + simulation mode)
  qc.py              — Real-time quality control tracking
  qc_monitor.py      — Live matplotlib QC dashboard (run in second terminal)
  ratings.py         — VAS rating scales (keyboard-controlled, MRI-compatible)
  run_block.py       — Single block execution (cycle loop, 10Hz updates, logging)
  run_experiment.py  — Main entry point (GUI, trigger, block runner)
  README.md          — This file
  data/              — Output directory (created automatically)
```

## Configuration Reference

All parameters are in `config.py`. Key settings:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `baseline_temp` | 30.0 | Baseline temperature (C) |
| `temp_min` / `temp_max` | 10.0 / 50.0 | Safety clamp bounds (C) |
| `max_delta` | 20.0 | Waveform amplitude (C) |
| `ramp_rate` | 1.0 | Hardware ramp speed (C/s) |
| `cycle_duration` | 80.0 | Duration of one stimulation cycle (s) |
| `cycles_per_block` | 8 | Number of cycles per block |
| `baseline_buffer` | 30.0 | Baseline duration before/after stimulation (s) |
| `update_hz` | 10 | Thermode command update frequency (Hz) |
| `TR` | 1.5 | Scanner repetition time (s) |
| `dummy_volumes` | 4 | Dummy volumes to discard after trigger |
| `trigger_key` | `'5'` | Scanner trigger key |
| `nontgi_mask` | `'P1_W'` | NonTGI mask for this participant |
| `tgi_mask` | `'TGI_1'` | TGI mask for this participant |
| `nontgi_warm_first` | `True` | Block order counterbalancing |
| `com_port` | `'COM6'` | TCS thermode serial port |
| `simulation` | `True` | Simulate thermode (no hardware) |
| `vas_enabled` | `False` | Show VAS ratings after each block (disabled for pilot) |
| `vas_max_duration` | 8.0 | Timeout per VAS question (s) |
| `fullscreen` | `False` | Fullscreen display (set `True` for scanner) |

## Counterbalancing

Two levels of counterbalancing across participants:

1. **Mask assignment** (between-subjects): each participant gets one NonTGI mask and one TGI mask, set in `config.py`.
2. **NonTGI block order** (between-subjects): `nontgi_warm_first = True` (Group A) runs warm-first before cool-first; `False` (Group B) reverses the order. TGI blocks always follow NonTGI.

Both sweep directions (warm-first and cool-first) are run within-subject to enable cancellation of HRF delay in pRF analysis.

## Timing Summary

| Phase | Duration |
|-------|----------|
| Dummy volumes | 6.0 s (4 x 1.5s TR) |
| Pre-block baseline | 30 s |
| Stimulation (8 cycles x 80s) | 640 s |
| Post-block baseline | 30 s |
| VAS ratings (3 x 8s max) | ~24 s |
| **Total per block** | **~730 s (~12.2 min)** |
| **Total session (4 blocks)** | **~49 min** (plus inter-block breaks) |
