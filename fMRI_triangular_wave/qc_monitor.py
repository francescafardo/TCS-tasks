"""
Real-time QC monitor for thermode experiment.

Displays a live matplotlib dashboard with two panels:
    1. Zone temperatures — actual thermode readings (prominent) with
       commanded temperatures as faint reference lines
    2. Temperature error — |commanded - actual| per active zone

Usage:
    python qc_monitor.py                        # auto-detect latest thermode file
    python qc_monitor.py path/to/thermode.tsv   # explicit file
"""

import sys
import os
import json
import glob
import csv

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# ---------------------------------------------------------------------------
# Column indices (must match JSON sidecar "Columns" order)
# ---------------------------------------------------------------------------
COL_ONSET = 0
COL_VOLUME = 1
COL_BLOCK_INDEX = 2
COL_BLOCK_TYPE = 3
COL_CYCLE_INDEX = 4
COL_MASK_NAME = 5
COL_WARM_FIRST = 6
COL_DELTA = 7
COL_Z1_SET = 8
COL_Z5_SET = 12
COL_Z1_ACT = 13
COL_Z5_ACT = 17

ZONE_COLORS = ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00']
ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5']


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_latest_thermode_file():
    """Find the most recently modified *_thermode_*.tsv under data/."""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    pattern = os.path.join(data_dir, '**', '*_thermode_*.tsv')
    matches = glob.glob(pattern, recursive=True)
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def find_json_sidecar(tsv_path):
    """Return the JSON sidecar path for a thermode TSV (same name, .json)."""
    base = tsv_path.rsplit('.tsv', 1)[0]
    json_path = base + '.json'
    if os.path.exists(json_path):
        return json_path
    return None


def load_sidecar(json_path):
    """Load experiment metadata from the JSON sidecar."""
    with open(json_path, 'r') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Data reading
# ---------------------------------------------------------------------------

def read_thermode_data(filepath):
    """Read thermode TSV, tolerating partial last line.

    Returns a list of rows (each row a list of strings), skipping any
    incomplete trailing line.
    """
    rows = []
    try:
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                # A valid row has 18 columns
                if len(row) == 18:
                    rows.append(row)
    except Exception:
        pass
    return rows


def parse_rows(rows):
    """Convert raw string rows to typed numpy arrays.

    Returns dict with keys:
        onset, delta, cycle_index,
        zone_set (5xN), zone_act (5xN),
        mask_name (str, from first row)
    or None if no data.
    """
    if not rows:
        return None

    n = len(rows)
    onset = np.empty(n)
    delta = np.empty(n)
    cycle_index = np.empty(n, dtype=int)
    zone_set = np.empty((5, n))
    zone_act = np.empty((5, n))
    mask_name = rows[0][COL_MASK_NAME]

    for i, row in enumerate(rows):
        try:
            onset[i] = float(row[COL_ONSET])
            delta[i] = float(row[COL_DELTA])
            cycle_index[i] = int(row[COL_CYCLE_INDEX])
            for z in range(5):
                zone_set[z, i] = float(row[COL_Z1_SET + z])
                zone_act[z, i] = float(row[COL_Z1_ACT + z])
        except (ValueError, IndexError):
            # Partial or malformed row — truncate here
            onset = onset[:i]
            delta = delta[:i]
            cycle_index = cycle_index[:i]
            zone_set = zone_set[:, :i]
            zone_act = zone_act[:, :i]
            break

    return {
        'onset': onset,
        'delta': delta,
        'cycle_index': cycle_index,
        'zone_set': zone_set,
        'zone_act': zone_act,
        'mask_name': mask_name,
    }


def detect_active_zones(data):
    """Return list of zone indices where commanded temp differs from baseline.

    A zone is active if its set temperature ever differs from the mode
    (most common value, i.e. the baseline).
    """
    active = []
    for z in range(5):
        vals = data['zone_set'][z]
        if len(vals) == 0:
            continue
        # If all values are identical, zone is inactive
        if np.ptp(vals) > 0.5:
            active.append(z)
    return active


# ---------------------------------------------------------------------------
# Figure setup
# ---------------------------------------------------------------------------

def create_figure(filepath, sidecar):
    """Create the 2-panel figure and return (fig, axes, line_objects)."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={'height_ratios': [3, 1]})
    fig.subplots_adjust(hspace=0.25, top=0.92, bottom=0.08, left=0.08,
                        right=0.95)

    # Build title from sidecar metadata
    if sidecar:
        title = (f"QC Monitor — {sidecar.get('block_type', '?')} | "
                 f"{sidecar.get('mask_name', '?')} | "
                 f"{'warm-first' if sidecar.get('warm_first') else 'cool-first'}")
    else:
        title = f"QC Monitor — {os.path.basename(filepath)}"
    fig.suptitle(title, fontsize=12, fontweight='bold')

    # --- Top: Zone temperatures (actual prominent, commanded faint) ---
    ax0 = axes[0]
    ax0.set_ylabel('Temperature (°C)')
    ax0.set_title('Zone temperatures', fontsize=10)
    ax0.grid(True, alpha=0.3)

    lines_act = []
    lines_set = []
    for z in range(5):
        la, = ax0.plot([], [], color=ZONE_COLORS[z], linewidth=2.5,
                       label=f'{ZONE_LABELS[z]} actual')
        ls, = ax0.plot([], [], color=ZONE_COLORS[z], linewidth=1.5,
                       linestyle=':', alpha=0.4,
                       label=f'{ZONE_LABELS[z]} cmd')
        lines_act.append(la)
        lines_set.append(ls)

    baseline_temp = sidecar.get('baseline_temp', 30.0) if sidecar else 30.0
    max_delta = sidecar.get('max_delta', 17.5) if sidecar else 17.5
    y_min_fixed = baseline_temp - max_delta - 2
    y_max_fixed = baseline_temp + max_delta + 2
    ax0.set_ylim(y_min_fixed, y_max_fixed)
    ax0.axhline(baseline_temp, color='grey', linestyle='--', linewidth=1.5,
                alpha=0.4, label='baseline')

    # --- Bottom: Temperature error ---
    ax1 = axes[1]
    ax1.set_xlabel('Time from trigger (s)')
    ax1.set_ylabel('|Cmd − Act| (°C)')
    ax1.set_title('Temperature error', fontsize=10)
    ax1.set_ylim(-0.2, 5)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(2.0, color='red', linestyle='--', linewidth=1.5, alpha=0.6,
                label='warning (2°C)')

    lines_err = []
    for z in range(5):
        le, = ax1.plot([], [], color=ZONE_COLORS[z], linewidth=2.0,
                       label=ZONE_LABELS[z])
        lines_err.append(le)

    line_objects = {
        'zone_act': lines_act,
        'zone_set': lines_set,
        'zone_err': lines_err,
    }

    return fig, axes, line_objects


# ---------------------------------------------------------------------------
# Animation update
# ---------------------------------------------------------------------------

def make_update(filepath, axes, line_objects, state):
    """Return the FuncAnimation update function (closure over state)."""

    def update(frame):
        rows = read_thermode_data(filepath)
        data = parse_rows(rows)
        if data is None or len(data['onset']) == 0:
            return []

        onset = data['onset']
        active = detect_active_zones(data)

        # Update x-axis limits
        t_max = onset[-1]
        for ax in axes:
            ax.set_xlim(0, max(t_max + 5, 10))

        # --- Zone temperatures ---
        for z in range(5):
            if z in active:
                line_objects['zone_act'][z].set_data(onset, data['zone_act'][z])
                line_objects['zone_set'][z].set_data(onset, data['zone_set'][z])
            else:
                line_objects['zone_act'][z].set_data([], [])
                line_objects['zone_set'][z].set_data([], [])

        # Build legend only once
        if not state.get('legend_set') and active:
            handles = []
            labels = []
            for z in active:
                handles.append(line_objects['zone_act'][z])
                labels.append(f'{ZONE_LABELS[z]} actual')
                handles.append(line_objects['zone_set'][z])
                labels.append(f'{ZONE_LABELS[z]} cmd')
            axes[0].legend(handles, labels, loc='upper right', fontsize=7,
                           ncol=len(active))
            axes[1].legend(loc='upper right', fontsize=7)
            state['legend_set'] = True

        # --- Temperature error ---
        for z in range(5):
            if z in active:
                err = np.abs(data['zone_set'][z] - data['zone_act'][z])
                line_objects['zone_err'][z].set_data(onset, err)
            else:
                line_objects['zone_err'][z].set_data([], [])

        # Update sample count in title
        # Cycle counter: count completed cycles from cycle_index column
        # cycle_index = -1 during baseline, 0-based during stimulation
        stim_mask = data['cycle_index'] >= 0
        if np.any(stim_mask):
            current_cycle = int(data['cycle_index'][stim_mask][-1])
            # A cycle is "completed" once the next one starts or baseline resumes
            unique_cycles = set(data['cycle_index'][stim_mask])
            last_sample_cycle = int(data['cycle_index'][-1])
            # If last sample is baseline (-1), all seen cycles are done
            if last_sample_cycle < 0:
                completed = len(unique_cycles)
            else:
                completed = max(0, len(unique_cycles) - 1)
            total = state.get('total_cycles', '?')
            axes[0].set_title(
                f'Zone temperatures — cycle {completed} of {total} completed',
                fontsize=10)
        else:
            axes[0].set_title('Zone temperatures — baseline', fontsize=10)

        return []

    return update


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Resolve thermode file
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = find_latest_thermode_file()
        if filepath is None:
            print('ERROR: No thermode TSV files found in data/.')
            print('Usage: python qc_monitor.py [path/to/thermode.tsv]')
            sys.exit(1)

    filepath = os.path.abspath(filepath)
    print(f'Monitoring: {filepath}')

    if not os.path.exists(filepath):
        print(f'ERROR: File not found: {filepath}')
        sys.exit(1)

    # Load JSON sidecar for metadata
    json_path = find_json_sidecar(filepath)
    sidecar = load_sidecar(json_path) if json_path else None
    if sidecar:
        print(f'Sidecar:   {json_path}')
        print(f'Block:     {sidecar.get("block_type")} | '
              f'{sidecar.get("mask_name")} | '
              f'{"warm-first" if sidecar.get("warm_first") else "cool-first"}')
    else:
        print('WARNING: No JSON sidecar found; using defaults.')

    # Create figure
    fig, axes, line_objects = create_figure(filepath, sidecar)
    state = {
        'total_cycles': sidecar.get('cycles_per_block', '?') if sidecar else '?',
    }

    update_fn = make_update(filepath, axes, line_objects, state)

    # Initial draw
    update_fn(0)

    ani = animation.FuncAnimation(fig, update_fn, interval=2000, cache_frame_data=False)
    plt.show()


if __name__ == '__main__':
    main()
