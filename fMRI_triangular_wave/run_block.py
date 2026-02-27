"""
Core block execution: cycle loop with 10Hz thermode updates and logging.

Each block uses a single mask for all cycles. The waveform is either
warm-first (delta starts at 0, rising) or cool-first (phase-shifted,
delta starts at max_delta, falling).

Thermode data is written to a BIDS _thermode.tsv (no header; columns
defined in companion JSON sidecar). Real-time QC tracks ramp rate,
onset latency, and temperature error.
"""

from psychopy import core, event, visual

from waveform import generate_delta_waveform, phase_shift_waveform, apply_mask
from qc import ThermalQC


def run_block(block_idx, block_type, mask_name, mask_array, warm_first,
              n_blocks, thermode, win, global_clock, trigger_time,
              physio_writer, config, physio_file=None):
    """Run one stimulation block (8 cycles, single mask).

    Returns
    -------
    dict with keys:
        timings : list of dict
            Phase timings for the BIDS events file.
        qc_summaries : list of dict
            Per-cycle QC metrics.
    """
    n_cycles = config['cycles_per_block']
    update_hz = config['update_hz']
    cycle_duration = config['cycle_duration']
    sample_interval = 1.0 / update_hz
    samples_per_cycle = int(cycle_duration * update_hz)
    baseline_temp = config['baseline_temp']

    # Generate waveform (same for all cycles in this block)
    waveform = generate_delta_waveform(cycle_duration, update_hz,
                                       config['max_delta'])
    if not warm_first:
        waveform = phase_shift_waveform(waveform)

    # Fixation point (small circle at screen centre)
    fixation = visual.Circle(win, radius=0.01, edges=32,
                             lineColor='white', fillColor='lightGrey',
                             pos=(0, 0))

    # Status text (bottom of screen, for experimenter reference)
    status_text = visual.TextStim(win, text='', pos=(0, -0.35), height=0.03,
                                  color='grey', wrapWidth=1.8)
    direction = 'warm-first' if warm_first else 'cool-first'

    # Quality control tracker
    qc = ThermalQC(config)

    # Track phase timings for BIDS events
    timings = []

    # --- Pre-block baseline ---
    pre_onset = global_clock.getTime() - trigger_time
    _run_baseline_period(config['baseline_buffer'], thermode, win, fixation,
                         status_text, global_clock, trigger_time, config,
                         physio_writer, block_idx, block_type, mask_name,
                         warm_first, n_blocks, physio_file=physio_file)
    pre_end = global_clock.getTime() - trigger_time
    timings.append({
        'onset': pre_onset,
        'duration': pre_end - pre_onset,
        'trial_type': 'baseline',
    })

    # --- Stimulation cycles ---
    stim_onset = global_clock.getTime() - trigger_time
    flush_counter = 0

    for cycle_idx in range(n_cycles):
        cycle_clock = core.Clock()
        qc.start_cycle(cycle_idx)

        for sample_idx in range(samples_per_cycle):
            target_time = sample_idx * sample_interval

            delta = float(waveform[sample_idx])
            temps = apply_mask(delta, mask_array, baseline_temp,
                               config['temp_min'], config['temp_max'])

            thermode.set_temperatures(temps)
            actual = thermode.get_temperatures()

            t_now = global_clock.getTime()
            t_from_trigger = t_now - trigger_time
            volume = int(t_from_trigger / config['TR']) + 1

            # QC update
            qc.update(t_from_trigger, temps, actual, delta, mask_array)

            # Write thermode data row (no header; columns in JSON sidecar)
            physio_writer.writerow([
                f'{t_from_trigger:.4f}',
                volume,
                block_idx,
                block_type,
                cycle_idx,
                mask_name,
                int(warm_first),
                f'{delta:.4f}',
                f'{temps[0]:.2f}', f'{temps[1]:.2f}', f'{temps[2]:.2f}',
                f'{temps[3]:.2f}', f'{temps[4]:.2f}',
                f'{actual[0]}', f'{actual[1]}', f'{actual[2]}',
                f'{actual[3]}', f'{actual[4]}',
            ])

            # Flush every 10 samples (~1s) for live QC monitor
            flush_counter += 1
            if physio_file is not None and flush_counter % 10 == 0:
                physio_file.flush()

            # Display
            fixation.draw()
            status_text.text = (
                f"Block {block_idx + 1}/{n_blocks} [{block_type}] "
                f"({direction}) | "
                f"Cycle {cycle_idx + 1}/{n_cycles} | "
                f"{mask_name} | "
                f"D={delta:.1f} | "
                f"Z: {temps[0]:.0f} {temps[1]:.0f} {temps[2]:.0f}"
                f" {temps[3]:.0f} {temps[4]:.0f}"
            )
            status_text.draw()
            win.flip()

            keys = event.getKeys(keyList=['escape'])
            if keys:
                raise KeyboardInterrupt("Escape pressed")

            elapsed = cycle_clock.getTime() - target_time
            wait_time = sample_interval - elapsed
            if wait_time > 0:
                core.wait(wait_time)

        # End-of-cycle QC summary
        cycle_summary = qc.end_cycle()
        print(f'  Cycle {cycle_idx + 1}/{n_cycles} QC: '
              f'onset_lat={cycle_summary["onset_latency_s"]:.2f}s, '
              f'ramp={cycle_summary["mean_ramp_rate"]:.2f} deg/s, '
              f'warm={cycle_summary["mean_warming_rate"]:.2f}, '
              f'cool={cycle_summary["mean_cooling_rate"]:.2f}, '
              f'err={cycle_summary["mean_temp_error"]:.2f} C, '
              f'flags={cycle_summary["n_ramp_flags"]}')

    stim_end = global_clock.getTime() - trigger_time
    timings.append({
        'onset': stim_onset,
        'duration': stim_end - stim_onset,
        'trial_type': 'stimulation',
    })

    # --- Post-block baseline ---
    post_onset = global_clock.getTime() - trigger_time
    _run_baseline_period(config['baseline_buffer'], thermode, win, fixation,
                         status_text, global_clock, trigger_time, config,
                         physio_writer, block_idx, block_type, mask_name,
                         warm_first, n_blocks, label='Post-block baseline',
                         physio_file=physio_file)
    post_end = global_clock.getTime() - trigger_time
    timings.append({
        'onset': post_onset,
        'duration': post_end - post_onset,
        'trial_type': 'baseline',
    })

    return {
        'timings': timings,
        'qc_summaries': qc.get_block_summaries(),
    }


def _run_baseline_period(duration, thermode, win, fixation, status_text,
                         global_clock, trigger_time, config, physio_writer,
                         block_idx, block_type, mask_name, warm_first,
                         n_blocks, label='Baseline', physio_file=None):
    """Hold baseline temperature for a specified duration."""
    update_hz = config['update_hz']
    sample_interval = 1.0 / update_hz
    n_samples = int(duration * update_hz)
    baseline_temps = [config['baseline_temp']] * 5

    thermode.set_baseline()
    baseline_clock = core.Clock()

    for i in range(n_samples):
        target_time = i * sample_interval

        thermode.set_temperatures(baseline_temps)
        actual = thermode.get_temperatures()

        t_now = global_clock.getTime()
        t_from_trigger = t_now - trigger_time
        volume = int(t_from_trigger / config['TR']) + 1

        physio_writer.writerow([
            f'{t_from_trigger:.4f}',
            volume,
            block_idx,
            f'{block_type}_baseline',
            -1,
            mask_name,
            int(warm_first),
            '0.0000',
            f'{baseline_temps[0]:.2f}', f'{baseline_temps[1]:.2f}',
            f'{baseline_temps[2]:.2f}', f'{baseline_temps[3]:.2f}',
            f'{baseline_temps[4]:.2f}',
            f'{actual[0]}', f'{actual[1]}', f'{actual[2]}',
            f'{actual[3]}', f'{actual[4]}',
        ])

        # Flush every 10 samples (~1s) for live QC monitor
        if physio_file is not None and (i + 1) % 10 == 0:
            physio_file.flush()

        fixation.draw()
        status_text.text = (
            f"Block {block_idx + 1}/{n_blocks} [{block_type}] | {label}"
        )
        status_text.draw()
        win.flip()

        keys = event.getKeys(keyList=['escape'])
        if keys:
            raise KeyboardInterrupt("Escape pressed")

        elapsed = baseline_clock.getTime() - target_time
        wait_time = sample_interval - elapsed
        if wait_time > 0:
            core.wait(wait_time)
