"""Validate probe.loudness against published EBU Tech 3341 / BS.1770 cases.

    python -m pytest tests/test_loudness.py -v

These are absolute references, not self-consistency checks. BS.1770-4 defines a
997 Hz sine at -23 dBFS peak in each channel of a stereo pair as reading exactly
-23.0 LUFS, which only comes out right if the K-weighting filters and the
-0.691 constant are both correct. A K-filter gain error of half a dB fails these
tests.
"""

from __future__ import annotations

import numpy as np
import pytest

from probe.audioio import Audio, AudioMeta
from probe.loudness import _high_shelf, _highpass, crest_factor_db, integrated_loudness, k_weight

SR = 48000
TOLERANCE = 0.3


def _audio(samples: np.ndarray, sample_rate: int = SR) -> Audio:
    if samples.ndim == 1:
        samples = samples[:, None]
    meta = AudioMeta(
        path=None,  # type: ignore[arg-type]
        codec="pcm_f32",
        sample_rate=sample_rate,
        channels=samples.shape[1],
        duration_s=samples.shape[0] / sample_rate,
        bits_per_sample=32,
        lossy=False,
    )
    return Audio(samples=samples.astype(np.float32), sample_rate=sample_rate, meta=meta)


def _sine(amplitude: float, seconds: float, hz: float = 997.0, sample_rate: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * hz * t)


def test_reference_sine_reads_minus_23_lufs():
    """BS.1770-4 reference: 997 Hz, -23 dBFS peak per channel, stereo -> -23.0 LUFS."""
    amplitude = 10.0 ** (-23.0 / 20.0)
    signal = _sine(amplitude, 20.0)
    stereo = np.repeat(signal[:, None], 2, axis=1)
    result = integrated_loudness(_audio(stereo))
    assert result["lufsIntegrated"] == pytest.approx(-23.0, abs=TOLERANCE)


def test_reference_sine_scales_with_level():
    """Halving the amplitude must lower the reading by 6.02 dB, exactly."""
    amplitude = 10.0 ** (-23.0 / 20.0)
    stereo = np.repeat(_sine(amplitude, 20.0)[:, None], 2, axis=1)
    reference = integrated_loudness(_audio(stereo))["lufsIntegrated"]
    quieter = np.repeat(_sine(amplitude / 2.0, 20.0)[:, None], 2, axis=1)
    scaled = integrated_loudness(_audio(quieter))["lufsIntegrated"]
    assert scaled == pytest.approx(reference - 6.0206, abs=0.05)


def test_mono_and_stereo_channel_weights():
    """Both use weight 1.0, so the same sine in two channels reads 3.01 dB higher."""
    amplitude = 10.0 ** (-23.0 / 20.0)
    mono = integrated_loudness(_audio(_sine(amplitude, 20.0)))["lufsIntegrated"]
    stereo = integrated_loudness(_audio(np.repeat(_sine(amplitude, 20.0)[:, None], 2, axis=1)))["lufsIntegrated"]
    assert stereo == pytest.approx(mono + 3.0103, abs=0.1)


def test_loudness_range_of_ten_step_alternation():
    """20 s alternating -23/-33 LUFS passages: LRA about 10 LU, integrated -25.8.

    The integrated value is the mean of the two passages' powers, which lands
    near -25.8, not at -23. The relative gate leaves both passages in.
    """
    amplitude = 10.0 ** (-23.0 / 20.0)
    loud = _sine(amplitude, 20.0)
    quiet = _sine(amplitude / 10.0 ** (10.0 / 20.0), 20.0)  # -33 LUFS
    stereo = np.repeat(np.concatenate([loud, quiet])[:, None], 2, axis=1)
    result = integrated_loudness(_audio(stereo))
    assert result["lufsIntegrated"] == pytest.approx(-25.8, abs=1.0)
    assert result["lra"] == pytest.approx(10.0, abs=1.0)


def test_quiet_signal_falls_below_the_absolute_gate():
    """Below -70 LUFS nothing is gated in, so no reading is produced."""
    stereo = np.repeat(_sine(10.0 ** (-80.0 / 20.0), 20.0)[:, None], 2, axis=1)
    assert integrated_loudness(_audio(stereo))["lufsIntegrated"] is None


def test_k_weighting_shelf_has_unit_dc_gain():
    """Guards the sign convention: 0 dB at DC, +4 dB well above the shelf.

    The RBJ high-shelf uses opposite sign forms in its numerator and
    denominator. Mixing them up gives a DC gain near -9, so this is asserted
    directly rather than inferred from a sine response.
    """
    for rate in (44100, 48000):
        b0, b1, b2, a1, a2 = _high_shelf(rate)
        dc = (b0 + b1 + b2) / (1.0 + a1 + a2)
        assert dc == pytest.approx(1.0, abs=1e-6), f"DC gain {dc:.4f} at {rate} Hz"
        nyquist = (b0 - b1 + b2) / (1.0 - a1 + a2)
        assert 20.0 * np.log10(nyquist) == pytest.approx(4.0, abs=0.2)


def test_k_weighting_highpass_blocks_dc():
    """The RLB high-pass must leave nothing at DC and unity well above 38 Hz."""
    for rate in (44100, 48000):
        b0, b1, b2, a1, a2 = _highpass(rate)
        assert (b0 + b1 + b2) / (1.0 + a1 + a2) == pytest.approx(0.0, abs=1e-9)
        assert (b0 - b1 + b2) / (1.0 - a1 + a2) == pytest.approx(1.0, abs=0.01)


def test_k_weighting_matches_the_published_48k_coefficients():
    """Conformance check: at 48 kHz the published BS.1770 table is used verbatim."""
    from probe.loudness import HIGHPASS_REFERENCE, SHELF_REFERENCE

    assert _highpass(48000) == HIGHPASS_REFERENCE
    assert _high_shelf(48000) == SHELF_REFERENCE
    # The published table is self-consistent: the shelf is flat at DC and +4 dB
    # above its corner, the high-pass is zero at DC and flat above its corner.
    b0, b1, b2, a1, a2 = SHELF_REFERENCE
    assert (b0 + b1 + b2) / (1.0 + a1 + a2) == pytest.approx(1.0, abs=1e-6)
    assert 20.0 * np.log10((b0 - b1 + b2) / (1.0 - a1 + a2)) == pytest.approx(4.0, abs=0.01)
    b0, b1, b2, a1, a2 = HIGHPASS_REFERENCE
    assert (b0 + b1 + b2) / (1.0 + a1 + a2) == pytest.approx(0.0, abs=1e-12)
    # The published passband gain is +0.02 dB, not unity. Tolerance is loose
    # because a1/a2 are transcribed to 14 significant digits.
    assert (b0 - b1 + b2) / (1.0 - a1 + a2) == pytest.approx(1.00499, abs=1e-5)


def test_non_reference_rates_still_design_sane_filters():
    """44.1 kHz has no tabulated coefficients, so the analytic path must hold up."""
    for rate in (44100, 96000):
        b0, b1, b2, a1, a2 = _high_shelf(rate)
        assert (b0 + b1 + b2) / (1.0 + a1 + a2) == pytest.approx(1.0, abs=1e-6)
        b0, b1, b2, a1, a2 = _highpass(rate)
        assert (b0 + b1 + b2) / (1.0 + a1 + a2) == pytest.approx(0.0, abs=1e-9)
        assert (b0 - b1 + b2) / (1.0 - a1 + a2) == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize(
    "hz,low,high",
    [
        (60.0, -4.0, -1.5),  # the RLB high-pass is not a pure Butterworth; -2.9 dB here
        (997.0, -1.0, 1.0),  # the reference frequency is passed at unity
        (10000.0, 2.5, 4.5),  # the shelf settles near its +4 dB asymptote
    ],
)
def test_k_weighting_response_is_monotonic_where_it_must_be(hz: float, low: float, high: float):
    """Sanity-check the designed filters: cut the bass, boost the top, pass 997 Hz."""
    amplitude = 0.1
    mono = _sine(amplitude, 6.0, hz=hz)[:, None]
    filtered = k_weight(mono, SR)
    gain = 20.0 * np.log10(
        np.sqrt((filtered[SR // 2 :] ** 2).mean()) / np.sqrt((mono[SR // 2 :] ** 2).mean())
    )
    assert low < gain < high, f"{hz} Hz K-weighting gain {gain:.2f} dB outside ({low}, {high})"


def test_crest_factor_matches_definition():
    """A full-scale square wave has a crest factor of 0 dB; a sine has 3.01 dB."""
    amplitude = 0.5
    sine = _sine(amplitude, 4.0)
    assert crest_factor_db(_audio(sine)) == pytest.approx(3.01, abs=0.1)
    square = np.sign(_sine(amplitude, 4.0, hz=100.0)) * amplitude
    assert crest_factor_db(_audio(square)) == pytest.approx(0.0, abs=0.5)
