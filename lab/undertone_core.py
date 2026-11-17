"""Core signal processing for undertone.

Hides a voice V inside a cover C so that the mono mix (what a single
speaker plays) contains only the cover, while each earphone channel
carries the voice.

Three modes:
  classic   L = C + V          R = C - V
  oneear    L = 2C + V         R = -V
  perslice  per time-frequency slice, the cover moves to the left ear
            only where the voice is active:
            L = (1 + a)C + V   R = 2C - L   (a in [0, 1])

In every mode (L + R) / 2 == C exactly, so the voice cancels in mono.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
EPS = 1e-12


# ----------------------------------------------------------------- utilities

def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)) + EPS))


def to_db(x: float) -> float:
    return float(20 * np.log10(max(x, EPS)))


def from_db(d: float) -> float:
    return float(10 ** (d / 20))


def active_rms(x: np.ndarray, sr: int = SR, frame_s: float = 0.02,
               floor_db: float = -40.0) -> float:
    """RMS over frames that are within `floor_db` of the loudest frame.

    Ignores silence so a voice with pauses is measured by its spoken parts.
    """
    n = max(1, int(frame_s * sr))
    usable = len(x) // n * n
    if usable == 0:
        return rms(x)
    frames = x[:usable].reshape(-1, n)
    r = np.sqrt(np.mean(frames ** 2, axis=1) + EPS)
    keep = r > r.max() * from_db(floor_db)
    return float(np.sqrt(np.mean(r[keep] ** 2)))


def load_mono(path: str, sr: int = SR) -> np.ndarray:
    """Load any file libsndfile can read, mix to mono, resample to `sr`."""
    x, fs = sf.read(path, always_2d=True, dtype="float64")
    x = x.mean(axis=1)
    if fs != sr:
        g = gcd(int(fs), sr)
        x = signal.resample_poly(x, sr // g, int(fs) // g)
    return x


def fit_length(cover: np.ndarray, length: int, sr: int = SR,
               xfade_s: float = 0.05) -> np.ndarray:
    """Trim or loop the cover (with crossfades at loop points) to `length`."""
    if len(cover) >= length:
        return cover[:length].copy()
    xf = min(int(xfade_s * sr), len(cover) // 4)
    fade_in = np.linspace(0.0, 1.0, xf)
    out = cover.copy()
    while len(out) < length:
        joint = out[-xf:] * (1 - fade_in) + cover[:xf] * fade_in
        out = np.concatenate([out[:-xf], joint, cover[xf:]])
    return out[:length]


def fade(x: np.ndarray, sr: int = SR, fade_s: float = 0.03) -> np.ndarray:
    n = min(int(fade_s * sr), len(x) // 2)
    ramp = np.linspace(0.0, 1.0, n)
    y = x.copy()
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    return y


# --------------------------------------------------------------- voice shape

def shape_voice(v: np.ndarray, lowpass_hz: float | None, sr: int = SR,
                highpass_hz: float = 120.0) -> np.ndarray:
    """High-pass to remove rumble; optional low-pass (24 dB/oct) to reduce
    leakage on phones with two spaced speakers."""
    sos = signal.butter(4, highpass_hz, btype="highpass", fs=sr, output="sos")
    y = signal.sosfiltfilt(sos, v)
    if lowpass_hz:
        sos = signal.butter(4, lowpass_hz, btype="lowpass", fs=sr, output="sos")
        y = signal.sosfiltfilt(sos, y)
    return y


# ------------------------------------------------------------------- mixing

@dataclass
class Render:
    left: np.ndarray
    right: np.ndarray
    cover_ref: np.ndarray   # exactly what (L + R) / 2 should equal
    voice_ref: np.ndarray   # the voice as placed in the mix

    def stereo(self) -> np.ndarray:
        return np.stack([self.left, self.right], axis=1)


def _perslice(c: np.ndarray, v: np.ndarray, sr: int = SR,
              strength: float = 4.0, smooth_ms: float = 50.0
              ) -> tuple[np.ndarray, np.ndarray]:
    """Move the cover into the left ear only in slices where the voice is."""
    nper, hop = 2048, 512
    kw = dict(fs=sr, window="hann", nperseg=nper, noverlap=nper - hop)
    _, _, cs = signal.stft(c, **kw)
    _, _, vs = signal.stft(v, **kw)
    a = np.clip(strength * np.abs(vs) / (np.abs(cs) + EPS), 0.0, 1.0)
    # smooth over time (~smooth_ms) and 3 frequency bins to avoid warbling
    t_frames = max(1, int(round(smooth_ms / 1000 * sr / hop)))
    a = signal.convolve2d(a, np.ones((3, t_frames)) / (3 * t_frames),
                          mode="same", boundary="symm")
    _, left = signal.istft((1 + a) * cs + vs, **kw)
    left = left[: len(c)]
    if len(left) < len(c):
        left = np.pad(left, (0, len(c) - len(left)))
    right = 2 * c - left  # guarantees (L + R) / 2 == C to the last bit
    return left, right


def render(voice: np.ndarray, cover: np.ndarray, *, mode: str,
           level_db: float, lowpass_hz: float | None, sr: int = SR,
           lead_s: float = 1.5, tail_s: float = 1.5,
           cover_peak_db: float = -6.0, out_peak_db: float = -3.0) -> Render:
    v = shape_voice(voice, lowpass_hz, sr)
    lead, tail = int(lead_s * sr), int(tail_s * sr)
    total = lead + len(v) + tail

    c = fit_length(cover, total, sr)
    c = c / (np.max(np.abs(c)) + EPS) * from_db(cover_peak_db)

    vf = np.zeros(total)
    vf[lead: lead + len(v)] = v
    vf *= active_rms(c, sr) * from_db(level_db) / (active_rms(v, sr) + EPS)

    c, vf = fade(c, sr), fade(vf, sr)

    if mode == "classic":
        left, right = c + vf, c - vf
    elif mode == "oneear":
        left, right = 2 * c + vf, -vf
    elif mode == "perslice":
        left, right = _perslice(c, vf, sr)
    else:
        raise ValueError(f"unknown mode: {mode}")

    g = from_db(out_peak_db) / (max(np.max(np.abs(left)), np.max(np.abs(right))) + EPS)
    return Render(left * g, right * g, c * g, vf * g)


# --------------------------------------------------------------- demo input

def demo_voice(seconds: float = 4.0, sr: int = SR, seed: int = 1) -> np.ndarray:
    """Speech-like test signal: gliding harmonics shaped by a syllable rhythm."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    f0 = 140 + 30 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    x = sum(np.sin(k * phase) / k for k in range(1, 25))
    sos = signal.butter(2, [400, 1200], btype="bandpass", fs=sr, output="sos")
    x = x + 2 * signal.sosfilt(sos, x)  # crude formant
    syll = np.clip(np.sin(2 * np.pi * 4 * t), 0, None) ** 2
    gaps = np.repeat(rng.random(int(seconds * 2) + 1) > 0.25, sr // 2)[: len(t)]
    return x * syll * gaps


def demo_cover(seconds: float = 8.0, sr: int = SR, seed: int = 2) -> np.ndarray:
    """Rain-like pink noise plus a soft chord bed."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    white = rng.standard_normal(n)
    b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], \
           [1, -2.494956002, 2.017265875, -0.522189400]
    pink = signal.lfilter(b, a, white)
    t = np.arange(n) / sr
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6)) * 0.05
    return pink / np.max(np.abs(pink)) + chord
