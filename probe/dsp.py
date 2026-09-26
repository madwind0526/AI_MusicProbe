"""Dependency-light DSP fingerprint.

None of these metrics claims to know whether a track is AI-generated. They
measure *what the processing chain did to the signal*, which is the part that
has to be separated out before any AI-vs-human verdict is believable.

Every metric is scale-relative: band energies are referenced to the track's own
median band level, so a mastering gain change does not register as a spectral
change. Absolute levels live in the separate `levels` group.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audioio import Audio
from .config import (
    COMB_ENVELOPE_HZ,
    COMB_ENABLED,
    COMB_HARMONIC_MIN_DB,
    COMB_HARMONIC_TOLERANCE_HZ,
    COMB_MAX_SPACING_HZ,
    COMB_MIN_ANALYSIS_HZ,
    COMB_MIN_HARMONICS,
    COMB_MIN_SPACING_HZ,
    COMB_STRONG_DB,
    HOP,
    N_FFT,
    PEAK_MAX_COUNT,
    PEAK_MIN_HZ,
    PEAK_PROMINENCE_DB,
    PEAK_SMOOTH_BINS,
    PEAK_VALLEY_WINDOW,
    TILT_BANDS,
)

_EPS = 1e-12

# A frequency counts as digitally silent when it sits this far below the median
# level of the in-band spectrum. Natural music does not reach it inside the
# passband; resampling and lossy codecs do.
NULL_REL_DB = -60.0

# A slope steeper than this (dB per kHz, averaged over a 500 Hz span) is a
# brickwall rather than natural rolloff.
BRICKWALL_DB_PER_KHZ = -20.0
BRICKWALL_SPAN_HZ = 500.0


@dataclass(frozen=True)
class Spectrum:
    freqs: np.ndarray
    mag: np.ndarray  # (frames, bins), linear magnitude
    frame_db: np.ndarray  # (frames,), per-frame level in dB

    @property
    def mean_db(self) -> np.ndarray:
        return _to_db(self.mag.mean(axis=0))


def _to_db(values: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(values), _EPS))


def _box_filter(values: np.ndarray, width: int) -> np.ndarray:
    """Centred moving average that preserves length for any width.

    The padding is asymmetric on purpose: a symmetric pad of width//2 on each
    side only lines up for odd widths, and every computed width here is derived
    from a frequency, so even widths are the common case.
    """
    if width <= 1:
        return values
    width = min(int(width), values.size)
    left = width // 2
    right = width - 1 - left
    padded = np.pad(values, (left, right), mode="edge")
    kernel = np.ones(width, dtype=np.float64) / width
    filtered = np.convolve(padded, kernel, mode="valid")
    if filtered.size != values.size:  # width was clamped to the signal length
        filtered = np.resize(filtered, values.size)
    return filtered


def magnitude_spectrum(audio: Audio) -> Spectrum:
    """Hann-windowed STFT of the mono downmix, computed in bounded blocks."""
    x = audio.mono()
    if x.size < N_FFT:
        x = np.pad(x, (0, N_FFT - x.size))

    window = np.hanning(N_FFT).astype(np.float32)
    frame_count = 1 + (x.size - N_FFT) // HOP
    if frame_count < 1:
        frame_count = 1

    freqs = np.fft.rfftfreq(N_FFT, d=1.0 / audio.sample_rate)
    block = 512
    chunks: list[np.ndarray] = []
    for start in range(0, frame_count, block):
        stop = min(start + block, frame_count)
        offsets = np.arange(start, stop) * HOP
        frames = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[offsets]
        spectrum = np.fft.rfft(frames * window, axis=1)
        chunks.append(np.abs(spectrum).astype(np.float32))
        del frames, spectrum

    mag = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, freqs.size), dtype=np.float32)
    frame_db = _to_db(mag.sum(axis=1)) if mag.size else np.zeros(0, dtype=np.float64)
    return Spectrum(freqs=freqs, mag=mag, frame_db=frame_db)


def band_levels_db(spectrum: Spectrum, bands=TILT_BANDS) -> dict[str, float]:
    freqs = spectrum.freqs
    mag = spectrum.mag
    out: dict[str, float] = {}
    for low, high in bands:
        mask = (freqs >= low) & (freqs < high)
        if not mask.any():
            continue
        # Energy, not amplitude: a band's level is its total power in dB.
        out[f"{low:g}-{high:g}"] = float(10.0 * np.log10(max(float((mag[:, mask] ** 2).sum()), _EPS)))
    return out


def spectral_tilt_db_per_octave(spectrum: Spectrum) -> float:
    """Least-squares slope of band level against log2(frequency centre).

    A single number that moves when EQ, resampling or a vocoder tilts the
    spectrum, which makes it a good chain-effect indicator.
    """
    freqs = spectrum.freqs
    mag = spectrum.mag
    xs: list[float] = []
    ys: list[float] = []
    for low, high in TILT_BANDS:
        mask = (freqs >= low) & (freqs < high)
        if not mask.any():
            continue
        level = 10.0 * np.log10(max(float((mag[:, mask] ** 2).sum()), _EPS))
        xs.append(np.log2(float(freqs[mask].mean())))
        ys.append(level)
    if len(xs) < 3:
        return 0.0
    return float(np.polyfit(np.asarray(xs), np.asarray(ys), 1)[0])


def _in_band_median_db(spectrum: Spectrum, nyquist: float) -> float:
    mask = spectrum.freqs <= min(nyquist, 20000.0)
    if not mask.any():
        return 0.0
    levels = 10.0 * np.log10(np.maximum(spectrum.mag.mean(axis=0)[mask], _EPS))
    return float(np.median(levels))


def steepest_rolloff(spectrum: Spectrum, nyquist: float) -> dict[str, float | None]:
    """Locate the sharpest sustained drop in the mean spectrum.

    Resampling and lossy coding leave a brickwall at the source Nyquist. Natural
    spectra roll off gradually, so the steepest sustained slope is a direct
    readout of that boundary rather than a statistical estimate.
    """
    freqs = spectrum.freqs
    mask = freqs <= nyquist
    if not mask.any():
        return {"hz": None, "dbPerKhz": None}
    f = freqs[mask]
    db = spectrum.mean_db[mask]

    smooth = _box_filter(db, PEAK_SMOOTH_BINS)
    if smooth.size < 3:
        return {"hz": None, "dbPerKhz": None}

    span_hz = max(f[1] - f[0], 1e-9) * PEAK_VALLEY_WINDOW
    width = max(int(round(BRICKWALL_SPAN_HZ / span_hz)), 1)
    slope = np.gradient(smooth, f) * 1000.0  # dB per kHz
    slope = _box_filter(slope, width)

    # Ignore DC: a click or a DC step can dominate the raw gradient.
    valid = np.ones(slope.size, dtype=bool)
    valid[: max(int(20.0 / (f[1] - f[0])), 1)] = False
    if not valid.any():
        return {"hz": None, "dbPerKhz": None}

    idx = int(np.argmin(np.where(valid, slope, np.inf)))
    return {"hz": round(float(f[idx]), 1), "dbPerKhz": round(float(slope[idx]), 2)}


def energy_rolloff_hz(spectrum: Spectrum, nyquist: float, fraction: float = 0.99) -> float | None:
    mask = spectrum.freqs <= nyquist
    if not mask.any():
        return None
    power = (spectrum.mag[:, mask] ** 2).sum(axis=0)
    total = power.sum()
    if total <= 0:
        return None
    cumulative = np.cumsum(power) / total
    index = int(np.searchsorted(cumulative, fraction))
    index = min(index, spectrum.freqs.size - 1)
    return round(float(spectrum.freqs[index]), 1)


def digital_null_hz(spectrum: Spectrum, nyquist: float) -> float | None:
    """Highest frequency still within NULL_REL_DB of the in-band median level."""
    freqs = spectrum.freqs
    mask = freqs <= nyquist
    if not mask.any():
        return None
    f = freqs[mask]
    levels = spectrum.mean_db[mask]
    reference = _in_band_median_db(spectrum, nyquist)
    above = levels >= reference + NULL_REL_DB
    if not above.any():
        return None
    return round(float(f[np.max(np.nonzero(above))]), 1)


def spectral_comb(spectrum: Spectrum, nyquist: float, sample_rate: int) -> dict:
    """Look for a periodic comb in the mean spectrum's envelope residual.

    A transposed-convolution upsampler stamps the output with a comb: the same
    narrow peak repeats at every multiple of the final stride frequency, and the
    stride comes from the architecture, not from the training data.

    Peak-picking does not work here. The time-averaged magnitude spectrum of
    ordinary music is smooth, so any hand-set prominence threshold either fires
    on every natural bump or on nothing. Subtracting a wide spectral envelope
    instead leaves the comb alone in the residual, and the residual's own
    spectrum then shows the stride as a single strong component. No threshold is
    involved in finding it.
    """
    freqs = spectrum.freqs
    mask = (freqs >= COMB_MIN_ANALYSIS_HZ) & (freqs <= nyquist)
    if int(mask.sum()) < 64:
        return _empty_comb("분석 대역이 너무 좁음")

    f = freqs[mask]
    db = spectrum.mean_db[mask]
    bin_hz = float(f[1] - f[0])

    envelope = _box_filter(db, max(int(round(COMB_ENVELOPE_HZ / bin_hz)), 3))
    residual = db - envelope
    # Taper the band edges; the envelope estimate is unreliable there and the
    # resulting step would dominate the residual spectrum.
    taper = np.hanning(residual.size)
    residual = residual * taper
    if not np.any(residual):
        return _empty_comb("잔차가 전부 0")

    # Period(k) = N * bin_hz / k, so this axis is period in Hz, not frequency.
    # k = 0 is DC and has no period; it is parked at infinity so the band mask
    # drops it.
    size = residual.size
    magnitude = np.abs(np.fft.rfft(residual))
    period_axis = np.full(magnitude.size, np.inf)
    period_axis[1:] = (size * bin_hz) / np.arange(1, magnitude.size)
    band = (period_axis >= COMB_MIN_SPACING_HZ) & (period_axis <= min(COMB_MAX_SPACING_HZ, nyquist / 2))
    if not band.any():
        return _empty_comb("격자 간격 검색 범위 없음")

    band_magnitude = magnitude[band]
    band_period = period_axis[band]
    peak_index = int(np.argmax(band_magnitude))
    peak_magnitude = float(band_magnitude[peak_index])
    spacing = float(band_period[peak_index])

    # Depth relative to the comb's own neighbourhood, so a broad spectral tilt
    # does not read as a strong comb.
    floor = float(np.median(band_magnitude))
    depth = 20.0 * np.log10(max(peak_magnitude, _EPS) / max(floor, _EPS))

    harmonics, rising, orders = _comb_harmonics(f, db, spacing, bin_hz)
    strong = depth >= COMB_STRONG_DB and rising >= COMB_MIN_HARMONICS

    return {
        "spacingHz": round(spacing, 2),
        "depthDb": round(depth, 2),
        "harmonics": harmonics,
        "harmonicCount": rising,
        "ordersOnGrid": orders,
        "strong": strong,
        "note": (
            f"격자 {spacing:.1f}Hz, 깊이 {depth:.1f}dB. 아키텍처 지문으로 쓰일 수 있습니다."
            if strong
            else f"격자 {spacing:.1f}Hz, 깊이 {depth:.1f}dB로 신뢰 기준({COMB_STRONG_DB}dB / {COMB_MIN_HARMONICS}배수)에 미달합니다."
        ),
    }


def _empty_comb(note: str) -> dict:
    return {
        "spacingHz": None, "depthDb": None, "harmonics": [], "harmonicCount": 0,
        "ordersOnGrid": 0, "strong": False, "note": note,
    }


def _comb_harmonics(
    freqs: np.ndarray, db: np.ndarray, spacing: float, bin_hz: float
) -> tuple[list[dict[str, float | int]], int, int]:
    """Measure how many multiples of the spacing actually rise above their surroundings.

    Returns the marked harmonics, how many clear COMB_HARMONIC_MIN_DB, and how
    many orders the spacing implies. The count of *rising* harmonics is the
    evidence: simply counting the orders that exist would report a full band as
    a match and prove nothing.
    """
    if spacing <= 0:
        return [], 0, 0
    orders = int(float(freqs[-1]) / spacing)
    if orders < 1:
        return [], 0, 0
    bin_width = max(int(round(COMB_HARMONIC_TOLERANCE_HZ / bin_hz)), 1)

    out: list[dict[str, float | int]] = []
    rising = 0
    for order in range(1, orders + 1):
        index = int(round((order * spacing - freqs[0]) / bin_hz))
        lo = max(index - bin_width, 0)
        hi = min(index + bin_width + 1, freqs.size)
        if lo >= hi:
            continue
        local = int(lo + np.argmax(db[lo:hi]))
        level = float(db[local])
        neighbours = np.concatenate((db[lo:local], db[local + 1 : hi]))
        baseline = float(np.mean(neighbours)) if neighbours.size else level
        rise = level - baseline
        if rise >= COMB_HARMONIC_MIN_DB:
            rising += 1
            out.append({
                "order": order,
                "hz": round(float(freqs[local]), 1),
                "riseDb": round(rise, 2),
            })
    return out, rising, orders


def artifact_fingerprint(spectrum: Spectrum, nyquist: float, limit: int | None = PEAK_MAX_COUNT) -> list[dict[str, float | int]]:
    """Strongest local maxima of the mean log spectrum, for display only.

    Real music spectra are bumpy, so this list carries little evidence on its
    own. `spectral_comb` is the measurement; this is only here so the UI can put
    a marker on the chart.
    """
    freqs = spectrum.freqs
    mask = (freqs >= PEAK_MIN_HZ) & (freqs <= nyquist)
    if not mask.any():
        return []
    f = freqs[mask]
    db = spectrum.mean_db[mask]
    smooth = _box_filter(db, PEAK_SMOOTH_BINS)
    if smooth.size < 5:
        return []

    left = np.roll(smooth, 1)
    right = np.roll(smooth, -1)
    interior = np.zeros(smooth.size, dtype=bool)
    interior[2:-2] = True
    is_peak = (smooth > left) & (smooth >= right) & interior
    if not is_peak.any():
        return []

    width = min(PEAK_VALLEY_WINDOW, smooth.size)
    peaks: list[dict[str, float | int]] = []
    for index in np.nonzero(is_peak)[0]:
        lo = max(int(index) - width, 0)
        hi = min(int(index) + width, smooth.size)
        valley = max(float(smooth[lo:int(index)].min()), float(smooth[int(index) + 1 : hi].min()))
        prominence = float(smooth[index]) - valley
        if prominence < PEAK_PROMINENCE_DB:
            continue
        peaks.append(
            {
                "hz": round(float(f[index]), 1),
                "hzNorm": round(float(f[index]) / nyquist, 5),
                "prominenceDb": round(prominence, 2),
            }
        )

    peaks.sort(key=lambda p: p["prominenceDb"], reverse=True)  # type: ignore[arg-type]
    return peaks[:limit] if limit else peaks


def transient_metrics(spectrum: Spectrum) -> dict[str, float | None]:
    """Spectral-flux attack statistics.

    Diffusion and vocoder output differ from human recording in how abruptly
    onsets rise, so the flux distribution is worth tracking across stages.
    """
    if spectrum.mag.shape[0] < 4:
        return {"fluxP95Db": None, "fluxCrestDb": None, "onsetCount": None}

    diff = np.diff(spectrum.mag, axis=0)
    flux = _to_db(np.maximum(diff, 0.0).sum(axis=1))
    if flux.size == 0:
        return {"fluxP95Db": None, "fluxCrestDb": None, "onsetCount": None}

    median = float(np.median(flux))
    p95 = float(np.percentile(flux, 95))
    # A frame counts as an onset when its flux clears both the median and a
    # fraction of the dynamic range; a single threshold alone flags every frame.
    threshold = median + 0.5 * (p95 - median)
    onsets = int(np.count_nonzero(flux > threshold))
    return {
        "fluxP95Db": round(p95, 2),
        "fluxCrestDb": round(p95 - median, 2),
        "onsetCount": onsets,
    }


def noise_floor_db(spectrum: Spectrum) -> float | None:
    """Gap between the 95th and 5th percentile frame level."""
    if spectrum.frame_db.size < 8:
        return None
    return round(float(np.percentile(spectrum.frame_db, 95) - np.percentile(spectrum.frame_db, 5)), 2)


def stereo_metrics(audio: Audio) -> dict[str, float | None]:
    if audio.samples.shape[1] < 2:
        return {"correlation": None, "sideToMidDb": None, "channelBalanceDb": None}

    left = audio.samples[:, 0].astype(np.float64)
    right = audio.samples[:, 1].astype(np.float64)
    if left.size < 2:
        return {"correlation": None, "sideToMidDb": None, "channelBalanceDb": None}

    left_energy = float((left**2).sum())
    right_energy = float((right**2).sum())
    denominator = np.sqrt(max(left_energy, _EPS) * max(right_energy, _EPS))
    correlation = float((left * right).sum() / denominator)
    correlation = max(-1.0, min(1.0, correlation))

    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    mid_energy = float((mid**2).sum())
    side_energy = float((side**2).sum())
    side_to_mid = 10.0 * np.log10(max(side_energy, _EPS) / max(mid_energy, _EPS))

    total = max(left_energy + right_energy, _EPS)
    balance = 10.0 * np.log10(max(left_energy, _EPS) / max(right_energy, _EPS))
    del total
    return {
        "correlation": round(correlation, 4),
        "sideToMidDb": round(side_to_mid, 2),
        "channelBalanceDb": round(balance, 2),
    }


def level_metrics(audio: Audio) -> dict[str, float | None]:
    x = audio.mono()
    if x.size == 0:
        return {"peakDbfs": None, "rmsDbfs": None, "dcOffset": None, "truePeakDbfs": None}

    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    dc = float(np.mean(x))
    # A true-peak estimate needs 4x oversampling to catch inter-sample peaks;
    # linear interpolation of the cubic Hermite polynomial is close enough for a
    # relative comparison between stages.
    oversampled = _interpolate_4x(x)
    true_peak = float(np.max(np.abs(oversampled))) if oversampled.size else peak
    return {
        "peakDbfs": round(_db(peak), 2),
        "rmsDbfs": round(_db(rms), 2),
        "dcOffset": round(dc, 8),
        "truePeakDbfs": round(_db(true_peak), 2),
    }


def _interpolate_4x(x: np.ndarray) -> np.ndarray:
    if x.size < 4:
        return x
    positions = np.arange(x.size - 1) * 4
    grid = np.arange((x.size - 1) * 4, dtype=np.float64)
    return np.interp(grid, positions, x[:-1].astype(np.float64))


def _db(value: float) -> float:
    return 20.0 * np.log10(max(abs(value), _EPS))


CURVE_POINTS = 256
CURVE_MIN_HZ = 20.0


def log_spectrum_curve(spectrum: Spectrum, nyquist: float, points: int = CURVE_POINTS) -> dict[str, list[float]]:
    """Mean log-spectrum resampled onto a log frequency axis.

    Linear bins crowd all the resolution into the top octave, which is exactly
    the region the artifact peaks live in. Resampling to log frequency keeps the
    curve readable and the payload small enough to ship inside a JSON report.
    """
    freqs = spectrum.freqs
    mask = freqs >= CURVE_MIN_HZ
    if not mask.any():
        return {"hz": [], "db": []}
    f = freqs[mask]
    db = spectrum.mean_db[mask]

    top = min(nyquist, float(f[-1]))
    if top <= CURVE_MIN_HZ:
        return {"hz": [], "db": []}
    grid = np.geomspace(CURVE_MIN_HZ, top, points)
    sampled = np.interp(np.log(grid), np.log(f), db)
    return {
        "hz": [round(float(v), 1) for v in grid],
        "db": [round(float(v), 2) for v in sampled],
    }


def analyze(audio: Audio) -> dict:
    """Full DSP profile for one decoded file."""
    spectrum = magnitude_spectrum(audio)
    nyquist = audio.sample_rate / 2.0
    bands = band_levels_db(spectrum)
    reference = float(np.median(list(bands.values()))) if bands else 0.0
    peaks = artifact_fingerprint(spectrum, nyquist)

    profile = {
        "meta": audio.meta.as_dict(),
        "spectral": {
            "rolloff99Hz": energy_rolloff_hz(spectrum, nyquist),
            "steepestRolloff": steepest_rolloff(spectrum, nyquist),
            "digitalNullHz": digital_null_hz(spectrum, nyquist),
            "tiltDbPerOctave": round(spectral_tilt_db_per_octave(spectrum), 3),
            "bandLevelsRelDb": {k: round(v - reference, 2) for k, v in bands.items()},
            "curve": log_spectrum_curve(spectrum, nyquist),
        },
        "artifactFingerprint": peaks,
        "transient": transient_metrics(spectrum),
        "noiseFloorDb": noise_floor_db(spectrum),
        "stereo": stereo_metrics(audio),
        "levels": level_metrics(audio),
    }

    if COMB_ENABLED:
        # Not a validated discriminator. Kept for the record, not for scoring.
        profile["artifactComb"] = spectral_comb(spectrum, nyquist, audio.sample_rate)
    return profile


__all__ = [
    "Spectrum",
    "analyze",
    "artifact_fingerprint",
    "band_levels_db",
    "digital_null_hz",
    "energy_rolloff_hz",
    "log_spectrum_curve",
    "magnitude_spectrum",
    "noise_floor_db",
    "spectral_comb",
    "spectral_tilt_db_per_octave",
    "steepest_rolloff",
    "stereo_metrics",
    "transient_metrics",
]
