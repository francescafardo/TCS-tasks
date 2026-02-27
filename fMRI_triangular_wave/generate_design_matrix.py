#!/usr/bin/env python3
"""
Generate fMRI design matrices for the thermal pRF experiment.

Produces per-run design matrices for GLM analysis and stimulus aperture
matrices for pRF analysis. Task regressors are deterministic (computed from
config.py), so design matrices can be generated before data collection.

GLM regressors (HRF-convolved, at TR resolution):
    stim_boxcar      — 1 during stimulation, 0 during baselines
    delta_centered   — triangular waveform amplitude (mean-centered)
    delta_derivative — rate of temperature change (dDelta/dt)

pRF stimulus aperture (unconvolved, at TR resolution):
    zone1–zone5      — per-zone commanded temperature

Output formats:
    *_design.tsv             — GLM design matrix (nilearn-compatible)
    *_design.npz             — all arrays (GLM + pRF, convolved + unconvolved)
    *_spm_regressors.mat     — SPM multiple regressors (R matrix + names)
    *_spm_prf_aperture.mat   — pRF aperture for SPM
    *_prf_aperture.tsv       — stimulus aperture for pRF fitting
    *_design.json            — metadata
    *_design.png             — visualization

Usage:
    python generate_design_matrix.py --sub 0001 --ses 01
    python generate_design_matrix.py --sub 0001 --ses 01 --run 01
    python generate_design_matrix.py --sub 0001 --ses 01 --n-volumes 480

Requires: numpy, scipy, matplotlib
"""

import os
import sys
import json
import argparse

import numpy as np
from scipy.stats import gamma as gamma_dist
from scipy.io import savemat

from config import CONFIG
from masks import get_mask


# ---------------------------------------------------------------------------
# HRF
# ---------------------------------------------------------------------------

def spm_hrf(dt, time_length=32.0):
    """SPM canonical double-gamma HRF.

    Parameters
    ----------
    dt : float
        Sampling interval in seconds.
    time_length : float
        Duration of the HRF kernel in seconds.

    Returns
    -------
    hrf : np.ndarray
        Normalized HRF kernel sampled at dt.
    """
    t = np.arange(0, time_length, dt)
    hrf = (gamma_dist.pdf(t, 6.0, scale=1.0) -
           gamma_dist.pdf(t, 16.0, scale=1.0) / 6.0)
    if np.max(hrf) > 0:
        hrf = hrf / np.max(hrf)
    return hrf


# ---------------------------------------------------------------------------
# Block plan
# ---------------------------------------------------------------------------

def get_block_plan(config):
    """Return the 4-block sequence based on config."""
    nontgi_mask = config['nontgi_mask']
    tgi_mask = config['tgi_mask']
    if config['nontgi_warm_first']:
        return [
            {'block_type': 'NonTGI', 'mask_name': nontgi_mask,
             'warm_first': True},
            {'block_type': 'NonTGI', 'mask_name': nontgi_mask,
             'warm_first': False},
            {'block_type': 'TGI', 'mask_name': tgi_mask,
             'warm_first': True},
            {'block_type': 'TGI', 'mask_name': tgi_mask,
             'warm_first': False},
        ]
    else:
        return [
            {'block_type': 'NonTGI', 'mask_name': nontgi_mask,
             'warm_first': False},
            {'block_type': 'NonTGI', 'mask_name': nontgi_mask,
             'warm_first': True},
            {'block_type': 'TGI', 'mask_name': tgi_mask,
             'warm_first': True},
            {'block_type': 'TGI', 'mask_name': tgi_mask,
             'warm_first': False},
        ]


# ---------------------------------------------------------------------------
# Waveform (computed directly at arbitrary time resolution)
# ---------------------------------------------------------------------------

def triangle_delta(t, period, max_delta):
    """Triangular wave: 0 -> max_delta -> 0, repeating with given period."""
    return max_delta * (1.0 - np.abs(2.0 * (t % period) / period - 1.0))


# ---------------------------------------------------------------------------
# Design matrix generation
# ---------------------------------------------------------------------------

def compute_n_volumes(config):
    """Expected number of fMRI volumes per block (including dummies)."""
    total_s = (config['dummy_volumes'] * config['TR'] +
               config['baseline_buffer'] +
               config['cycles_per_block'] * config['cycle_duration'] +
               config['baseline_buffer'])
    return int(np.ceil(total_s / config['TR']))


def generate_run_design(config, mask_name, warm_first, n_volumes=None,
                        oversampling=16):
    """Generate all regressors for one run/block.

    Parameters
    ----------
    config : dict
        Experiment configuration.
    mask_name : str
        Mask name (e.g. 'P1_W', 'TGI_1').
    warm_first : bool
        True for warm-first, False for cool-first.
    n_volumes : int, optional
        Number of volumes. Computed from config if None.
    oversampling : int
        Temporal oversampling factor for HRF convolution.

    Returns
    -------
    dict with keys:
        frame_times, glm_convolved, glm_unconvolved,
        prf_aperture, prf_aperture_convolved, active_zones, metadata
    """
    TR = config['TR']
    if n_volumes is None:
        n_volumes = compute_n_volumes(config)

    total_time = n_volumes * TR
    dt = TR / oversampling
    n_hires = int(np.ceil(total_time / dt))
    t_hires = np.arange(n_hires) * dt

    # Key time points (seconds from trigger)
    dummy_end = config['dummy_volumes'] * TR
    stim_start = dummy_end + config['baseline_buffer']
    stim_dur = config['cycles_per_block'] * config['cycle_duration']
    stim_end = stim_start + stim_dur
    period = config['cycle_duration'] / 2.0  # 40s triangle period
    max_d = config['max_delta']

    # Volume onset times
    frame_times = np.arange(n_volumes) * TR

    # --- High-resolution neural signals ---

    # Stimulation boxcar
    stim_mask_hr = (t_hires >= stim_start) & (t_hires < stim_end)
    boxcar_hr = stim_mask_hr.astype(float)

    # Delta waveform (triangular wave during stimulation)
    delta_hr = np.zeros(n_hires)
    t_stim = t_hires - stim_start
    if not warm_first:
        t_stim = t_stim + period / 2.0  # phase shift for cool-first
    delta_hr[stim_mask_hr] = triangle_delta(
        t_stim[stim_mask_hr], period, max_d)

    # Mean-center delta within stimulation (orthogonalise vs boxcar)
    delta_ctr = delta_hr.copy()
    if np.any(stim_mask_hr):
        delta_ctr[stim_mask_hr] -= np.mean(delta_hr[stim_mask_hr])
    delta_ctr[~stim_mask_hr] = 0.0

    # Rate of change (dDelta/dt)
    ddelta_hr = np.gradient(delta_hr, dt)
    ddelta_ctr = ddelta_hr.copy()
    if np.any(stim_mask_hr):
        ddelta_ctr[stim_mask_hr] -= np.mean(ddelta_hr[stim_mask_hr])
    ddelta_ctr[~stim_mask_hr] = 0.0

    # Per-zone temperatures
    mask_arr = np.array(get_mask(mask_name), dtype=float)
    zone_hr = np.zeros((5, n_hires))
    for z in range(5):
        zone_hr[z] = config['baseline_temp'] + mask_arr[z] * delta_hr
        zone_hr[z] = np.clip(zone_hr[z], config['temp_min'],
                              config['temp_max'])

    # --- HRF convolution and downsampling ---
    hrf = spm_hrf(dt)
    tr_idx = np.minimum(np.round(frame_times / dt).astype(int), n_hires - 1)

    def conv_ds(sig):
        """Convolve with HRF and downsample to TR."""
        c = np.convolve(sig, hrf * dt)[:n_hires]
        return c[tr_idx]

    def ds(sig):
        """Downsample to TR without convolution."""
        return sig[tr_idx]

    # GLM regressors
    glm_conv = {
        'stim_boxcar': conv_ds(boxcar_hr),
        'delta_centered': conv_ds(delta_ctr),
        'delta_derivative': conv_ds(ddelta_ctr),
    }
    glm_unconv = {
        'stim_boxcar': ds(boxcar_hr),
        'delta': ds(delta_hr),
        'delta_centered': ds(delta_ctr),
        'delta_derivative': ds(ddelta_ctr),
    }

    # pRF aperture (time x 5 zones)
    prf_ap = np.column_stack([ds(zone_hr[z]) for z in range(5)])
    prf_ap_conv = np.column_stack([conv_ds(zone_hr[z]) for z in range(5)])

    active = [i for i in range(5) if mask_arr[i] != 0]

    meta = {
        'mask_name': mask_name,
        'mask_array': mask_arr.tolist(),
        'warm_first': bool(warm_first),
        'n_volumes': int(n_volumes),
        'n_dummy_volumes': int(config['dummy_volumes']),
        'TR': float(TR),
        'stim_start_s': float(stim_start),
        'stim_end_s': float(stim_end),
        'stim_duration_s': float(stim_dur),
        'baseline_buffer_s': float(config['baseline_buffer']),
        'cycle_duration_s': float(config['cycle_duration']),
        'cycles_per_block': int(config['cycles_per_block']),
        'max_delta': float(max_d),
        'baseline_temp': float(config['baseline_temp']),
        'active_zones': active,
    }

    return {
        'frame_times': frame_times,
        'glm_convolved': glm_conv,
        'glm_unconvolved': glm_unconv,
        'prf_aperture': prf_ap,
        'prf_aperture_convolved': prf_ap_conv,
        'active_zones': active,
        'metadata': meta,
    }


# ---------------------------------------------------------------------------
# Save functions
# ---------------------------------------------------------------------------

def save_design_tsv(filepath, design):
    """Save GLM design matrix as TSV (nilearn-compatible)."""
    ft = design['frame_times']
    gc = design['glm_convolved']
    header = 'frame_times\tstim_boxcar\tdelta_centered\tdelta_derivative'
    data = np.column_stack([
        ft, gc['stim_boxcar'], gc['delta_centered'], gc['delta_derivative'],
    ])
    np.savetxt(filepath, data, delimiter='\t', header=header,
               comments='', fmt='%.6f')
    print(f'  GLM design:      {filepath}')


def save_prf_aperture_tsv(filepath, design):
    """Save pRF stimulus aperture as TSV."""
    ft = design['frame_times']
    ap = design['prf_aperture']
    header = 'frame_times\tzone1\tzone2\tzone3\tzone4\tzone5'
    data = np.column_stack([ft, ap])
    np.savetxt(filepath, data, delimiter='\t', header=header,
               comments='', fmt='%.4f')
    print(f'  pRF aperture:    {filepath}')


def save_npz(filepath, design):
    """Save all arrays as numpy .npz archive."""
    np.savez(
        filepath,
        frame_times=design['frame_times'],
        glm_stim_boxcar=design['glm_convolved']['stim_boxcar'],
        glm_delta_centered=design['glm_convolved']['delta_centered'],
        glm_delta_derivative=design['glm_convolved']['delta_derivative'],
        unconv_stim_boxcar=design['glm_unconvolved']['stim_boxcar'],
        unconv_delta=design['glm_unconvolved']['delta'],
        unconv_delta_centered=design['glm_unconvolved']['delta_centered'],
        unconv_delta_derivative=design['glm_unconvolved']['delta_derivative'],
        prf_aperture=design['prf_aperture'],
        prf_aperture_convolved=design['prf_aperture_convolved'],
    )
    print(f'  NumPy archive:   {filepath}')


def save_spm_mat(filepath, design):
    """Save SPM-compatible .mat with R matrix for 'multiple regressors'."""
    gc = design['glm_convolved']
    R = np.column_stack([
        gc['stim_boxcar'], gc['delta_centered'], gc['delta_derivative'],
    ])
    names = np.array(['stim_boxcar', 'delta_centered', 'delta_derivative'],
                     dtype=object)
    savemat(filepath, {'R': R, 'names': names})
    print(f'  SPM regressors:  {filepath}')


def save_spm_prf_mat(filepath, design):
    """Save pRF aperture as SPM-compatible .mat."""
    savemat(filepath, {
        'aperture': design['prf_aperture'],
        'aperture_convolved': design['prf_aperture_convolved'],
        'zone_labels': np.array(
            ['zone1', 'zone2', 'zone3', 'zone4', 'zone5'], dtype=object),
        'frame_times': design['frame_times'],
    })
    print(f'  SPM pRF .mat:    {filepath}')


def save_metadata_json(filepath, design):
    """Save metadata as JSON."""
    with open(filepath, 'w') as f:
        json.dump(design['metadata'], f, indent=2)
    print(f'  Metadata:        {filepath}')


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_design_matrix(filepath, design, run_label=''):
    """Save design matrix visualization as PNG."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    ft = design['frame_times']
    gc = design['glm_convolved']
    gu = design['glm_unconvolved']
    ap = design['prf_aperture']
    meta = design['metadata']
    active = design['active_zones']

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(
        f'Design Matrix — {run_label}\n'
        f'{meta["mask_name"]} | '
        f'{"warm-first" if meta["warm_first"] else "cool-first"} | '
        f'{meta["n_volumes"]} volumes',
        fontsize=12, fontweight='bold')

    # Panel 1: unconvolved boxcar + raw delta
    ax = axes[0]
    ax.fill_between(ft, 0, gu['stim_boxcar'], alpha=0.15, color='grey',
                    label='stim boxcar')
    ax.plot(ft, gu['delta'] / meta['max_delta'], color='#e41a1c',
            linewidth=0.8, label='delta (normalised)')
    ax.set_ylabel('Neural signal')
    ax.set_title('Unconvolved regressors', fontsize=10)
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.2)

    # Panel 2: GLM convolved regressors (z-scored for display)
    ax = axes[1]
    colors = ['#333333', '#e41a1c', '#377eb8']
    names = ['stim_boxcar', 'delta_centered', 'delta_derivative']
    for name, color in zip(names, colors):
        vals = gc[name]
        std = np.std(vals)
        vals_z = (vals - np.mean(vals)) / std if std > 0 else vals
        ax.plot(ft, vals_z, color=color, linewidth=0.8, label=name)
    ax.set_ylabel('Z-scored amplitude')
    ax.set_title('GLM regressors (HRF-convolved)', fontsize=10)
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.2)

    # Panel 3: pRF aperture
    ax = axes[2]
    zone_colors = ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00']
    for z in active:
        ax.plot(ft, ap[:, z], color=zone_colors[z], linewidth=0.8,
                label=f'Zone {z + 1} (mask={int(meta["mask_array"][z]):+d})')
    ax.axhline(meta['baseline_temp'], color='grey', linestyle=':',
               alpha=0.5, label='baseline')
    ax.set_ylabel('Temperature (°C)')
    ax.set_title('pRF aperture (per-zone temperature, unconvolved)',
                 fontsize=10)
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.2)

    # Panel 4: design matrix image
    ax = axes[3]
    dm = np.column_stack([gc['stim_boxcar'], gc['delta_centered'],
                          gc['delta_derivative']])
    dm_z = dm.copy()
    for col in range(dm_z.shape[1]):
        std = np.std(dm_z[:, col])
        if std > 0:
            dm_z[:, col] = (dm_z[:, col] - np.mean(dm_z[:, col])) / std
    ax.imshow(dm_z.T, aspect='auto', cmap='RdBu_r', interpolation='nearest',
              extent=[ft[0], ft[-1], dm.shape[1] - 0.5, -0.5])
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(['boxcar', 'delta', 'dDelta/dt'])
    ax.set_xlabel('Time from trigger (s)')
    ax.set_title('GLM design matrix (z-scored)', fontsize=10)

    fig.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Plot:            {filepath}')


# ---------------------------------------------------------------------------
# Regressor correlation check
# ---------------------------------------------------------------------------

def print_correlations(design):
    """Print pairwise correlations between GLM regressors."""
    gc = design['glm_convolved']
    names = ['stim_boxcar', 'delta_centered', 'delta_derivative']
    vals = [gc[n] for n in names]
    print('  Regressor correlations (convolved):')
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = np.corrcoef(vals[i], vals[j])[0, 1]
            print(f'    {names[i]} vs {names[j]}: r = {r:.3f}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate fMRI design matrices for thermal pRF.')
    parser.add_argument('--sub', required=True,
                        help='Participant ID (e.g. 0001)')
    parser.add_argument('--ses', default='01',
                        help='Session number (default: 01)')
    parser.add_argument('--run', default=None,
                        help='Specific run (01-04). Omit for all 4.')
    parser.add_argument('--n-volumes', type=int, default=None,
                        help='Override number of volumes per run.')
    parser.add_argument('--no-plot', action='store_true',
                        help='Skip plot generation.')
    args = parser.parse_args()

    config = CONFIG.copy()
    block_plan = get_block_plan(config)

    if args.run is not None:
        run_idx = int(args.run) - 1
        if run_idx < 0 or run_idx >= len(block_plan):
            print(f'ERROR: run must be 01-{len(block_plan):02d}')
            sys.exit(1)
        runs = [(run_idx, block_plan[run_idx])]
    else:
        runs = list(enumerate(block_plan))

    out_dir = os.path.join(os.path.dirname(__file__) or '.', 'data',
                           f'sub-{args.sub}', f'ses-{args.ses}', 'func')
    os.makedirs(out_dir, exist_ok=True)

    for run_idx, block in runs:
        run_num = f'{run_idx + 1:02d}'
        prefix = f'sub-{args.sub}_ses-{args.ses}_task-tprf_run-{run_num}'
        direction = 'warm-first' if block['warm_first'] else 'cool-first'

        print(f'\n=== Run {run_num}: {block["block_type"]} | '
              f'{block["mask_name"]} | {direction} ===')

        design = generate_run_design(
            config, block['mask_name'], block['warm_first'],
            n_volumes=args.n_volumes)

        n_vol = design['metadata']['n_volumes']
        print(f'  Volumes: {n_vol} ({n_vol * config["TR"]:.1f}s)')
        print(f'  Active zones: {design["active_zones"]}')
        print_correlations(design)

        # Save all formats
        save_design_tsv(
            os.path.join(out_dir, f'{prefix}_design.tsv'), design)
        save_prf_aperture_tsv(
            os.path.join(out_dir, f'{prefix}_prf_aperture.tsv'), design)
        save_npz(
            os.path.join(out_dir, f'{prefix}_design.npz'), design)
        save_spm_mat(
            os.path.join(out_dir, f'{prefix}_spm_regressors.mat'), design)
        save_spm_prf_mat(
            os.path.join(out_dir, f'{prefix}_spm_prf_aperture.mat'), design)
        save_metadata_json(
            os.path.join(out_dir, f'{prefix}_design.json'), design)

        if not args.no_plot:
            run_label = (f'Run {run_num}: {block["block_type"]} '
                         f'{block["mask_name"]} {direction}')
            plot_design_matrix(
                os.path.join(out_dir, f'{prefix}_design.png'),
                design, run_label)

    print(f'\nAll files saved to: {out_dir}')
    print(f'\nNote: Nuisance regressors (motion parameters, aCompCor, drift)')
    print(f'must be added after fMRI preprocessing.')


if __name__ == '__main__':
    main()
