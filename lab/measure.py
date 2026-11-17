"""Measure how well each file hides and reveals the voice.

Usage:
  python measure.py out/*.wav out/reencoded/*.wav

For each file it reports:
  leak    voice level in the mono mix (what a single speaker plays),
          relative to the mono mix. Lower is better; below -40 dB is clean.
  L / R   voice level in each earphone channel relative to everything else
          in that channel. Higher is easier to understand.

File names must start with the variant name produced by make_variants.py;
re-encoded copies use '<variant>__<codec>.wav'. References are read from
the 'refs' folder next to the original variants (override with --refs).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from undertone_core import EPS, SR, rms, to_db


def find_lag(x: np.ndarray, ref: np.ndarray, max_lag: int = 8000) -> int:
    """Samples by which x lags ref (codecs add delay)."""
    n = min(len(x), len(ref), SR * 10)
    corr = signal.correlate(x[:n], ref[:n], mode="full", method="fft")
    mid = n - 1
    lo, hi = max(0, mid - max_lag), min(len(corr), mid + max_lag + 1)
    return int(np.argmax(np.abs(corr[lo:hi]))) + lo - mid


def shift(x: np.ndarray, lag: int, length: int) -> np.ndarray:
    y = x[lag:] if lag >= 0 else np.pad(x, (-lag, 0))
    y = y[:length]
    return np.pad(y, (0, length - len(y)))


def voice_share_db(x: np.ndarray, c: np.ndarray, v: np.ndarray) -> float:
    """Level of the voice component in x versus everything else in x, dB.

    Fits x ~ a*c + b*v jointly so chance correlation between cover and
    voice isn't counted as voice.
    """
    basis = np.stack([c, v], axis=1)
    (a, b), *_ = np.linalg.lstsq(basis, x, rcond=None)
    part = b * v
    return max(to_db(rms(part)) - to_db(rms(x - part)), -120.0)


def measure(path: Path, refs_dir: Path) -> dict:
    variant = path.stem.split("__")[0]
    codec = path.stem.split("__")[1] if "__" in path.stem else "original"
    cover = sf.read(refs_dir / f"{variant}.cover.wav")[0]
    voice = sf.read(refs_dir / f"{variant}.voice.wav")[0]

    x, fs = sf.read(path, always_2d=True)
    if fs != SR:
        raise SystemExit(f"{path}: expected {SR} Hz, got {fs}")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)

    # The mono mix always equals the cover, so it gives the codec delay.
    lag = find_lag(x.mean(axis=1), cover)
    left = shift(x[:, 0], lag, len(cover))
    right = shift(x[:, 1], lag, len(cover))
    mono = (left + right) / 2

    return {
        "file": variant,
        "codec": codec,
        "leak_db": voice_share_db(mono, cover, voice),
        "left_db": voice_share_db(left, cover, voice),
        "right_db": voice_share_db(right, cover, voice),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--refs", help="folder with *.cover.wav / *.voice.wav")
    args = p.parse_args()

    rows = []
    for f in map(Path, args.files):
        if f.parent.name == "refs":
            continue
        refs = Path(args.refs) if args.refs else (
            f.parent.parent / "refs" if f.parent.name == "reencoded" else f.parent / "refs")
        rows.append(measure(f, refs))

    print(f"{'variant':30s} {'codec':16s} {'leak':>8s} {'L voice':>8s} {'R voice':>8s}  verdict")
    for r in sorted(rows, key=lambda r: (r["file"], r["codec"])):
        hidden = r["leak_db"] <= -40
        heard = max(r["left_db"], r["right_db"]) >= -20
        verdict = "OK" if hidden and heard else ("VOICE LOST" if not heard else "LEAKS")
        print(f"{r['file']:30s} {r['codec']:16s} {r['leak_db']:8.1f} "
              f"{r['left_db']:8.1f} {r['right_db']:8.1f}  {verdict}")


if __name__ == "__main__":
    main()
