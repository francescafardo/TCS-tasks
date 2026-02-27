"""
Real-time QC monitor for thermode experiment.

Displays a live matplotlib dashboard with three panels:
    1. Delta waveform (temperature modulation over time)
    2. Zone temperatures (commanded vs actual, active zones only)
    3. Temperature error per active zone

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
    """Create the 3-panel figure and return (fig, axes, line_objects)."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.subplots_adjust(hspace=0.3, top=0.92, bottom=0.08, left=0.08,
                        right=0.95)

    # Build title from sidecar metadata
    if sidecar:
        title = (f"QC Monitor — {sidecar.get('block_type', '?')} | "
                 f"{sidecar.get('mask_name', '?')} | "
                 f"{'warm-first' if sidecar.get('warm_first') else 'cool-first'}")
    else:
        title = f"QC Monitor — {os.path.basename(filepath)}"
    fig.suptitle(title, fontsize=12, fontweight='bold')

    # --- Top: Delta waveform ---
    ax0 = axes[0]
    ax0.set_ylabel('Delta (°C)')
    ax0.set_ylim(-1, 22)
    ax0.set_title('Delta waveform', fontsize=10)
    ax0.grid(True, alpha=0.3)
    line_delta, = ax0.plot([], [], color='#333333', linewidth=1)

    # --- Middle: Zone temperatures ---
    ax1 = axes[1]
    ax1.set_ylabel('Temperature (°C)')
    ax1.set_title('Zone temperatures (solid=commanded, dashed=actual)',
                  fontsize=10)
    ax1.grid(True, alpha=0.3)

    lines_set = []
    lines_act = []
    for z in range(5):
        ls, = ax1.plot([], [], color=ZONE_COLORS[z], linewidth=1.2,
                       label=f'{ZONE_LABELS[z]} cmd')
        la, = ax1.plot([], [], color=ZONE_COLORS[z], linewidth=1.0,
                       linestyle='--', alpha=0.7,
                       label=f'{ZONE_LABELS[z]} act')
        lines_set.append(ls)
        lines_act.append(la)

    baseline_temp = sidecar.get('baseline_temp', 30.0) if sidecar else 30.0
    ax1.axhline(baseline_temp, color='grey', linestyle=':', linewidth=0.8,
                alpha=0.5, label='baseline')

    # --- Bottom: Temperature error ---
    ax2 = axes[2]
    ax2.set_xlabel('Time from trigger (s)')
    ax2.set_ylabel('|Cmd − Act| (°C)')
    ax2.set_title('Temperature error per active zone', fontsize=10)
    ax2.set_ylim(-0.2, 5)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(2.0, color='red', linestyle='--', linewidth=0.8, alpha=0.6,
                label='warning (2°C)')

    lines_err = []
    for z in range(5):
        le, = ax2.plot([], [], color=ZONE_COLORS[z], linewidth=1.0,
                       label=ZONE_LABELS[z])
        lines_err.append(le)

    line_objects = {
        'delta': line_delta,
        'zone_set': lines_set,
        'zone_act': lines_act,
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
        delta = data['delta']
        active = detect_active_zones(data)

        # Update x-axis limits
        t_max = onset[-1]
        for ax in axes:
            ax.set_xlim(0, max(t_max + 5, 10))

        # --- Delta waveform ---
        line_objects['delta'].set_data(onset, delta)
        axes[0].set_ylim(min(-1, np.min(delta) - 1),
                         max(22, np.max(delta) + 1))

        # --- Zone temperatures ---
        y_min_temp = float('inf')
        y_max_temp = float('-inf')
        for z in range(5):
            if z in active:
                line_objects['zone_set'][z].set_data(onset, data['zone_set'][z])
                line_objects['zone_act'][z].set_data(onset, data['zone_act'][z])
                y_min_temp = min(y_min_temp,
                                 np.min(data['zone_set'][z]),
                                 np.min(data['zone_act'][z]))
                y_max_temp = max(y_max_temp,
                                 np.max(data['zone_set'][z]),
                                 np.max(data['zone_act'][z]))
            else:
                line_objects['zone_set'][z].set_data([], [])
                line_objects['zone_act'][z].set_data([], [])

        if y_min_temp != float('inf'):
            margin = 2
            axes[1].set_ylim(y_min_temp - margin, y_max_temp + margin)

        # Build legend only once
        if not state.get('legend_set') and active:
            handles = []
            labels = []
            for z in active:
                handles.append(line_objects['zone_set'][z])
                labels.append(f'{ZONE_LABELS[z]} cmd')
                handles.append(line_objects['zone_act'][z])
                labels.append(f'{ZONE_LABELS[z]} act')
            axes[1].legend(handles, labels, loc='upper right', fontsize=7,
                           ncol=len(active))
            axes[2].legend(loc='upper right', fontsize=7)
            state['legend_set'] = True

        # --- Temperature error ---
        for z in range(5):
            if z in active:
                err = np.abs(data['zone_set'][z] - data['zone_act'][z])
                line_objects['zone_err'][z].set_data(onset, err)
            else:
                line_objects['zone_err'][z].set_data([], [])

        # Update sample count in title
        axes[0].set_title(f'Delta waveform ({len(onset)} samples)', fontsize=10)

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
    state = {}

    update_fn = make_update(filepath, axes, line_objects, state)

    # Initial draw
    update_fn(0)

    ani = animation.FuncAnimation(fig, update_fn, interval=2000, cache_frame_data=False)
    plt.show()


if __name__ == '__main__':
    main()
