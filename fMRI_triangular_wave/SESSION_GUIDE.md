# Session Guide — fMRI Thermal pRF Experiment

Step-by-step instructions for running a full session (4 blocks) with the live QC monitor.

## Pre-Session Setup

### 1. Configure participant parameters

Edit `config.py` before launching:

```python
# Assign masks for this participant (counterbalanced across participants)
'nontgi_mask': 'P1_W',     # Options: P1_W, P1_C, P3_W, P3_C
'tgi_mask': 'TGI_1',       # Options: TGI_1, TGI_2

# Block order counterbalancing
'nontgi_warm_first': True,  # True = Group A, False = Group B
```

### 2. Set hardware mode

For **simulation** (testing without thermode/scanner):

```python
'simulation': True,
'emulate': True,        # space bar instead of scanner trigger
'fullscreen': False,
```

For **real scanning**:

```python
'simulation': False,
'emulate': False,
'com_port': 'COM6',     # adjust to your serial port
'fullscreen': True,
'screen_index': 1,      # projector screen
```

## Running a Block

### Terminal 1 — Experiment

```bash
cd fMRI_triangular_wave
python run_experiment.py
```

1. **Dialog 1**: enter participant ID (e.g. `0001`) and session (`01`)
2. **Dialog 2**: review block plan, select block to run, confirm hardware settings
3. **Trigger**: press space (emulation) or wait for scanner trigger (`5` key)
4. **Stimulation**: 30s baseline → 8 x 80s cycles → 30s baseline (~12 min)
5. **Ratings**: 3 VAS questions (8s timeout each)
6. Script exits — run again for the next block

### Terminal 2 — QC Monitor (open before starting the block)

```bash
cd fMRI_triangular_wave
python qc_monitor.py
```

The monitor auto-detects the most recent thermode TSV in `data/`. To target a specific file:

```bash
python qc_monitor.py data/sub-0001/ses-01/func/sub-0001_ses-01_task-tprf_run-01_thermode_*.tsv
```

The dashboard shows three live panels updated every 2 seconds:

| Panel | What to look for |
|-------|-----------------|
| **Delta waveform** | Clean triangular wave, 0–20 C range |
| **Zone temperatures** | Dashed (actual) tracking solid (commanded) closely |
| **Temperature error** | All zones below the red 2 C warning line |

### Timing reference

| Phase | Duration |
|-------|----------|
| Dummy volumes | 6 s |
| Pre-baseline | 30 s |
| Stimulation (8 cycles) | 640 s |
| Post-baseline | 30 s |
| VAS ratings | ~24 s |
| **Total per block** | **~12 min** |

## Full 4-Block Session

Run each block as a separate invocation of `run_experiment.py`. The block plan auto-tracks completion.

| Block | Run | Condition | Direction |
|-------|-----|-----------|-----------|
| 1 | `run-01` | NonTGI | warm-first (Group A) or cool-first (Group B) |
| 2 | `run-02` | NonTGI | cool-first (Group A) or warm-first (Group B) |
| 3 | `run-03` | TGI | warm-first |
| 4 | `run-04` | TGI | cool-first |

Between blocks:
- The QC monitor window can stay open — it will pick up the new file on next launch, or you can restart it
- Take breaks as needed; there is no inter-block timer
- Check the console QC output for each cycle (ramp rate, temp error, flags)

## Output Files

After each block, four files are saved to `data/sub-{ID}/ses-{session}/func/`:

```
sub-0001_ses-01_task-tprf_run-01_events_20260227T140000.tsv     # BIDS events
sub-0001_ses-01_task-tprf_run-01_thermode_20260227T140000.tsv   # 10 Hz thermode recording
sub-0001_ses-01_task-tprf_run-01_thermode_20260227T140000.json  # JSON sidecar (metadata)
sub-0001_ses-01_task-tprf_run-01_qc_20260227T140000.tsv         # per-cycle QC metrics
```

Re-running a block creates new files with a different timestamp (never overwrites).

## QC Checklist

After each block, verify in the console output:

- [ ] `onset_lat` is consistent across cycles (hardware response delay)
- [ ] `ramp` is close to 1.00 deg/s (expected ramp rate)
- [ ] `warm` and `cool` rates are similar (no large asymmetry)
- [ ] `err` stays below 2.0 C (mean temperature error)
- [ ] `flags=0` or very low (ramp rate deviation count)

In the QC monitor dashboard:

- [ ] Delta waveform is a clean triangle (no flat spots or jumps)
- [ ] Actual temperatures (dashed) closely follow commanded (solid)
- [ ] Temperature error stays below the 2 C red warning line
- [ ] Only active zones are plotted (inactive zones hidden)

## Troubleshooting

| Issue | Fix |
|-------|-----|
| QC monitor shows "No thermode TSV files found" | Start the experiment first — the TSV is created at launch |
| QC monitor shows stale data | Close and reopen `qc_monitor.py` to pick up the latest file |
| Monitor picks up wrong file | Pass the file path explicitly: `python qc_monitor.py path/to/file.tsv` |
| High temperature error in QC | Check thermode connections; may indicate hardware lag or communication issue |
| Escape pressed during block | Block aborts; thermode returns to baseline; data up to that point is saved |
