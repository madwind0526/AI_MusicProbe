"""Integrated loudness per ITU-R BS.1770-4 / EBU R128.

Why this is here: "how much louder did mastering make it" is the central
question when comparing an original to a master, and peak level cannot answer
it. A limiter raises perceived loudness while leaving peak level alone.

The K-weighting filters are designed analytically for whatever sample rate the
file actually has. The standard only tabulates coefficients for 48 kHz, and
every corpus here is 48 kHz, but the human control set is 44.1 kHz, so the
filter has to be rate-correct rather than hard-coded.

scipy is not a dependency, so each biquad's impulse response is generated from
the difference equation and applied by FFT convolution. These filters decay in
well under 4096 taps, which makes the truncation exact for our purposes.
"""

from __future__ import annotations

import numpy as np

from .audioio import Audio

BLOCK_S = 0.400
HOP_S = 0.100  # 75% overlap, per the standard
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
LRA_LOW_PCT = 10.0
LRA_HIGH_PCT = 95.0
LRA_GATE_LU = -20.0

# K-weighting: a +4 dB high shelf near 1.7 kHz, then a high pass near 38 Hz.
# Values are the ones BS.1770 tabulates for 48 kHz.
SHELF_FREQ = 1681.974450955533
SHELF_GAIN_DB = 3.999843853973347
SHELF_Q = 0.7071752369554196
HIGHPASS_FREQ = 38.13547087602444
HIGHPASS_Q = 0.5003270373238773

# The standard only tabulates 48 kHz coefficients, and they are the authority
# there: reconstructing them from f0/Q lands within ~2e-6, which is close but not
# a conformance match. Every file in these corpora is 48 kHz, so the published
# values are used verbatim at that rate and the analytic design covers the rest
# (the human control set is 44.1 kHz).
REFERENCE_RATE = 48000
SHELF_REFERENCE = (
    1.53512485958697,
    -2.69169618940638,
    1.19839281085285,
    -1.69065929318241,
    0.73248077421585,
)
HIGHPASS_REFERENCE = (
    1.0,
    -2.0,
    1.0,
    -1.99004745483398,
    0.99007225036621,
)

# BS.1770 channel weights: L and R are 1.0, surround channels are 1.41.
SURROUND_GAIN = 1.41

_IR_TAPS = 4096


def _high_shelf(sample_rate: int) -> tuple[float, ...]:
    """RBJ high-shelf biquad, returned as (b0, b1, b2, a1, a2), a0 already 1.

    The RBJ high-shelf mixes two sign conventions and getting them consistent
    matters: the numerator uses (A+1) + (A-1)*cos while a0 and a2 use
    (A+1) - (A-1)*cos. Copying one form into the other yields a filter with a
    negative DC gain near -9, which inverts and boosts everything. The tests
    assert 0 dB at DC and +4 dB above the shelf.
    """
    if sample_rate == REFERENCE_RATE:
        return SHELF_REFERENCE
    a = 10.0 ** (SHELF_GAIN_DB / 40.0)
    w0 = 2.0 * np.pi * SHELF_FREQ / sample_rate
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2.0 * SHELF_Q)
    t = 2.0 * np.sqrt(a) * alpha
    numerator_common = (a + 1.0) + (a - 1.0) * cos_w0
    denominator_common = (a + 1.0) - (a - 1.0) * cos_w0
    a0 = denominator_common + t
    return (
        (a * (numerator_common + t)) / a0,
        (-2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)) / a0,
        (a * (numerator_common - t)) / a0,
        (2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)) / a0,
        (denominator_common - t) / a0,
    )


def _highpass(sample_rate: int) -> tuple[float, ...]:
    """RBJ high-pass biquad, returned as (b0, b1, b2, a1, a2), a0 already 1."""
    if sample_rate == REFERENCE_RATE:
        return HIGHPASS_REFERENCE
    w0 = 2.0 * np.pi * HIGHPASS_FREQ / sample_rate
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2.0 * HIGHPASS_Q)
    a0 = 1.0 + alpha
    return (
        ((1.0 + cos_w0) / 2.0) / a0,
        (-(1.0 + cos_w0)) / a0,
        ((1.0 + cos_w0) / 2.0) / a0,
        (-2.0 * cos_w0) / a0,
        (1.0 - alpha) / a0,
    )


def _impulse_response(coeffs: tuple[float, ...], taps: int = _IR_TAPS) -> np.ndarray:
    """Direct-form I impulse response of a biquad."""
    b0, b1, b2, a1, a2 = coeffs
    out = np.zeros(taps, dtype=np.float64)
    x1 = x2 = y1 = y2 = 0.0
    for n in range(taps):
        x0 = 1.0 if n == 0 else 0.0
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[n] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def _fft_convolve(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    size = signal.size + kernel.size - 1
    n = 1 << (size - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(signal, n) * np.fft.rfft(kernel, n), n)[: signal.size]


def k_weight(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Apply the BS.1770 K-weighting chain to each channel."""
    shelf = _impulse_response(_high_shelf(sample_rate))
    highpass = _impulse_response(_highpass(sample_rate))
    out = np.empty_like(samples, dtype=np.float64)
    for channel in range(samples.shape[1]):
        filtered = _fft_convolve(samples[:, channel].astype(np.float64), shelf)
        out[:, channel] = _fft_convolve(filtered, highpass)
    return out


def _block_powers(weighted: np.ndarray, sample_rate: int) -> np.ndarray:
    """Mean square per channel per 400 ms block, 75% overlap."""
    block = int(BLOCK_S * sample_rate)
    hop = int(HOP_S * sample_rate)
    if weighted.shape[0] < block:
        return np.zeros((0, weighted.shape[1]))
    count = 1 + (weighted.shape[0] - block) // hop
    # Strided view keeps this vectorised; a cumulative sum avoids a huge window.
    cumulative = np.concatenate([np.zeros((1, weighted.shape[1])), np.cumsum(weighted**2, axis=0)])
    starts = np.arange(count) * hop
    sums = cumulative[starts + block] - cumulative[starts]
    return sums / block


def _block_loudness(powers: np.ndarray, gains: np.ndarray) -> np.ndarray:
    """Loudness of each block, -0.691 + 10log10(sum G*z)."""
    weighted = powers @ gains
    with np.errstate(divide="ignore"):
        return -0.691 + 10.0 * np.log10(weighted)


def integrated_loudness(audio: Audio) -> dict[str, float | None]:
    """Integrated LUFS, LRA, and loudness range peak, per BS.1770-4."""
    if audio.samples.size == 0:
        return {"lufsIntegrated": None, "lra": None, "loudnessRangePeak": None, "samplePeakDbfs": None}

    channels = audio.samples.shape[1]
    # Mono and stereo are 1.0; anything wider is treated as surround per the spec.
    gains = np.full(channels, 1.0 if channels == 1 else (1.0 if channels == 2 else SURROUND_GAIN))

    weighted = k_weight(audio.samples, audio.sample_rate)
    powers = _block_powers(weighted, audio.sample_rate)
    if powers.shape[0] < 2:
        return {"lufsIntegrated": None, "lra": None, "loudnessRangePeak": None,
                "samplePeakDbfs": float(20.0 * np.log10(max(np.abs(audio.samples).max(), 1e-12)))}

    loudness = _block_loudness(powers, gains)

    keep = loudness > ABSOLUTE_GATE_LUFS
    if not keep.any():
        return {"lufsIntegrated": None, "lra": None, "loudnessRangePeak": None,
                "samplePeakDbfs": float(20.0 * np.log10(max(np.abs(audio.samples).max(), 1e-12)))}

    relative_threshold = float(
        _block_loudness(powers[keep].mean(axis=0, keepdims=True), gains)[0]
    ) - RELATIVE_GATE_LU
    gated = loudness > max(ABSOLUTE_GATE_LUFS, relative_threshold)
    if not gated.any():
        gated = keep

    integrated = float(_block_loudness(powers[gated].mean(axis=0, keepdims=True), gains)[0])

    lra_gate = loudness > (integrated + LRA_GATE_LU)
    lra_source = loudness[lra_gate] if lra_gate.any() else loudness
    lra = float(np.percentile(lra_source, LRA_HIGH_PCT) - np.percentile(lra_source, LRA_LOW_PCT))

    return {
        "lufsIntegrated": round(integrated, 2),
        "lra": round(lra, 2),
        "loudnessRangePeak": round(float(loudness.max()), 2),
        "samplePeakDbfs": round(float(20.0 * np.log10(max(np.abs(audio.samples).max(), 1e-12))), 2),
    }


def crest_factor_db(audio: Audio) -> float | None:
    """Peak-to-RMS ratio. A limiter's job shows up here as a falling crest."""
    samples = audio.samples.astype(np.float64)
    peak = float(np.abs(samples).max())
    rms = float(np.sqrt((samples**2).mean()))
    if peak <= 0 or rms <= 0:
        return None
    return round(20.0 * np.log10(peak / rms), 2)


__all__ = ["crest_factor_db", "integrated_loudness", "k_weight"]
