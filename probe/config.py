"""Paths and DSP tuning constants for ai-music-probe."""

from __future__ import annotations

import os
from pathlib import Path

from .app_settings import load_settings

ROOT = Path(__file__).resolve().parent.parent
_USER_SETTINGS = load_settings()

MODELS_DIR = Path(os.environ.get("AIPROBE_MODELS_DIR", _USER_SETTINGS["paths"]["models"]))
CORPUS_DIR = Path(os.environ.get("AIPROBE_CORPUS_DIR", ROOT / "corpus"))
REPORTS_DIR = Path(os.environ.get("AIPROBE_REPORTS_DIR", _USER_SETTINGS["paths"]["reports"]))
SCRATCH_DIR = Path(os.environ.get("AIPROBE_SCRATCH_DIR", ROOT / "scratch"))

HOST = os.environ.get("AIPROBE_HOST", "127.0.0.1")
PORT = int(os.environ.get("AIPROBE_PORT", "8792"))

# Analysis never resamples. Stage rates are reported as-is so a resample or a
# codec ceiling stays visible instead of being normalised away.
N_FFT = 4096
HOP = 1024

# A band counts as "present" while it stays within this many dB of the strongest
# lower band. Used to locate the effective spectral ceiling.
CEILING_DROP_DB = 6.0
CEILING_MIN_HZ = 1000.0

# Artifact fingerprint tuning. Peak prominence is measured against the smoothed
# spectral valley, so the threshold is deliberately small.
PEAK_PROMINENCE_DB = 5.0
PEAK_MIN_HZ = 200.0
# High enough that a saturated list is rare. When it does saturate, the report
# says so: a truncated list makes the added/removed peak diff meaningless.
PEAK_MAX_COUNT = 24
PEAK_VALLEY_WINDOW = 24
PEAK_SMOOTH_BINS = 15

# Comb detection: a conv upsampler stamps a periodic lattice into the spectrum.
# The measurement is the periodicity of the envelope residual, not peak height.
COMB_ENVELOPE_HZ = 300.0
COMB_MIN_ANALYSIS_HZ = 50.0
COMB_MIN_SPACING_HZ = 15.0
COMB_MAX_SPACING_HZ = 2000.0
COMB_HARMONIC_TOLERANCE_HZ = 25.0
COMB_HARMONIC_MIN_DB = 3.0
COMB_MIN_HARMONICS = 4
# Max/median over ~1000 bins of a random spectrum already sits near 15dB, so a
# threshold below that measures nothing. 18dB clears the noise baseline and
# still leaves a wide margin under a real resampler comb (measured ~50dB).
COMB_STRONG_DB = 18.0
# The comb lattice was measured against a control and did not survive it. On an
# identical-audio pair (same PCM, .mp3 vs .wav) the reported spacing moved 237 ->
# 198 Hz and the harmonic count 24 -> 20, and it fired on 17/17 human tracks at a
# *higher* depth than on the generated ones. Whatever it is picking up, it is
# not the generator, so it is off by default. See knowledge/trouble-shooting.md.
COMB_ENABLED = False

# Octave-ish bands for spectral tilt, expressed as (low_hz, high_hz).
TILT_BANDS = (
    (31.25, 62.5),
    (62.5, 125.0),
    (125.0, 250.0),
    (250.0, 500.0),
    (500.0, 1000.0),
    (1000.0, 2000.0),
    (2000.0, 4000.0),
    (4000.0, 8000.0),
    (8000.0, 16000.0),
    (16000.0, 20000.0),
)

# A stage whose rate is below this is treated as a format-lock warning even when
# every stage of a run agrees on it.
STANDARD_RATE_HZ = 44100

AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif")

# Canonical stage order. Anything not listed sorts after these, alphabetically.
STAGE_ORDER = (
    "source",
    "master",
    "postprocess",
    "vocal_pre_svc",
    "instrumental",
    "vocal_post_svc",
    "final",
)
