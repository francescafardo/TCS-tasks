"""
VAS (Visual Analog Scale) ratings for post-block perceptual reports.

Three questions per block: cold intensity, warm intensity, burning intensity.
Uses keyboard control (left/right arrows to move, up arrow to confirm)
compatible with MRI button boxes.
"""

import time

import pyglet
from psychopy import visual, core

# Questions presented after each block
VAS_QUESTIONS = [
    {'key': 'cold',    'text': 'How intense was the COLD sensation?'},
    {'key': 'warm',    'text': 'How intense was the WARM sensation?'},
    {'key': 'burning', 'text': 'How intense was the BURNING sensation?'},
]


def collect_vas_ratings(win, global_clock, trigger_time, config):
    """Present VAS ratings and return responses.

    Parameters
    ----------
    win : visual.Window
        PsychoPy window.
    global_clock : core.Clock
        Experiment-wide clock.
    trigger_time : float
        Scanner trigger time for computing time_from_trigger.
    config : dict
        Must contain 'vas_max_duration' and 'vas_labels'.

    Returns
    -------
    list of dict
        One dict per question with keys: question, rating, rt, onset_s,
        onset_from_trigger_s.
    """
    max_duration = config['vas_max_duration']
    labels = config['vas_labels']
    results = []

    # Set up pyglet keyboard handler for continuous key tracking
    pyglet_keys = pyglet.window.key
    key_handler = pyglet_keys.KeyStateHandler()
    win.winHandle.push_handlers(key_handler)

    # "Too slow" text for timeouts
    too_slow_text = visual.TextStim(win, text='Too slow', pos=(0, 0),
                                    height=0.08, color='red')

    for q in VAS_QUESTIONS:
        # Create fresh RatingScale for each question
        vas = visual.RatingScale(
            win,
            low=0,
            high=100,
            marker='triangle',
            markerStart=50,
            lineColor='white',
            tickMarks=[0, 100],
            stretch=1.5,
            showAccept=False,
            tickHeight=1.5,
            textColor='white',
            precision=1,
            maxTime=0,  # we handle timeout ourselves
            markerColor='white',
            textSize=0.8,
            textFont='Arial',
            labels=labels,
            skipKeys=None,
            acceptKeys='up',
            noMouse=True,
        )

        question_text = visual.TextStim(win, text=q['text'], pos=(0, 0.3),
                                        height=0.06, color='white',
                                        wrapWidth=1.5)

        # Record onset
        onset_s = global_clock.getTime()
        onset_from_trigger = onset_s - trigger_time

        start_time = time.time()
        right_pressed = 0
        left_pressed = 0
        min_hold_frames = 10  # frames before key-hold starts repeating

        # Rating loop
        while vas.noResponse:
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                break

            # Keyboard movement (left/right arrows)
            if key_handler[pyglet_keys.RIGHT]:
                if right_pressed == 0 or right_pressed > min_hold_frames:
                    vas.markerPlacedAt += 1
                right_pressed += 1
            else:
                right_pressed = 0

            if key_handler[pyglet_keys.LEFT]:
                if left_pressed == 0 or left_pressed > min_hold_frames:
                    vas.markerPlacedAt -= 1
                left_pressed += 1
            else:
                left_pressed = 0

            # Clamp to scale bounds
            vas.markerPlacedAt = max(0, min(100, vas.markerPlacedAt))

            # Draw
            vas.draw()
            question_text.draw()
            win.flip()

        # Collect response
        rating = vas.getRating()
        rt = vas.getRT()

        if elapsed >= max_duration and vas.noResponse:
            rating = float('nan')
            rt = float('nan')
            too_slow_text.draw()
            win.flip()
            core.wait(1.0)

        results.append({
            'question': q['key'],
            'rating': rating,
            'rt': rt,
            'onset_s': onset_s,
            'onset_from_trigger_s': onset_from_trigger,
        })

    # Clean up handler
    win.winHandle.remove_handlers(key_handler)

    return results
