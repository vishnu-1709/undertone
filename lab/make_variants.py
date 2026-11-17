"""Generate undertone test files.

Usage:
  python make_variants.py --voice my_voice.wav --cover song.mp3 --out out
  python make_variants.py --demo --out out          # synthetic inputs

Writes one stereo WAV per (mode, low-pass, level) plus float reference
tracks in out/refs/ that measure.py uses.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from undertone_core import SR, demo_cover, demo_voice, load_mono, render


def lp_label(lp: float | None) -> str:
    return "lpnone" if lp is None else f"lp{int(lp)}"


def parse_lp(s: str) -> float | None:
    return None if s.lower() == "none" else float(s)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--voice", help="your recorded message (any format libsndfile reads)")
    p.add_argument("--cover", help="the cover track (song, rain, lo-fi...)")
    p.add_argument("--demo", action="store_true", help="use synthetic voice and cover")
    p.add_argument("--out", default="out")
    p.add_argument("--modes", nargs="+", default=["classic", "oneear", "perslice"])
    p.add_argument("--levels", nargs="+", type=float, default=[-10.0, -6.0],
                   help="voice level relative to cover, dB")
    p.add_argument("--lowpass", nargs="+", type=parse_lp,
                   default=[None, 1500.0, 1000.0], help="Hz, or 'none'")
    args = p.parse_args()

    if args.demo:
        voice, cover = demo_voice(), demo_cover()
    elif args.voice and args.cover:
        voice, cover = load_mono(args.voice), load_mono(args.cover)
    else:
        p.error("give --voice and --cover, or --demo")

    out = Path(args.out)
    refs = out / "refs"
    refs.mkdir(parents=True, exist_ok=True)

    for mode in args.modes:
        for lp in args.lowpass:
            for level in args.levels:
                name = f"{mode}_{lp_label(lp)}_v{int(level)}"
                r = render(voice, cover, mode=mode, level_db=level, lowpass_hz=lp)
                sf.write(out / f"{name}.wav", r.stereo(), SR, subtype="PCM_16")
                sf.write(refs / f"{name}.cover.wav", r.cover_ref, SR, subtype="FLOAT")
                sf.write(refs / f"{name}.voice.wav", r.voice_ref, SR, subtype="FLOAT")
                mono = (r.left + r.right) / 2
                residual = np.max(np.abs(mono - r.cover_ref))
                print(f"{name:32s} peak {np.max(np.abs(r.stereo())):.3f}  "
                      f"mono residual {residual:.1e}")

    print(f"\nWrote {len(args.modes) * len(args.lowpass) * len(args.levels)} files to {out}/")


if __name__ == "__main__":
    main()
