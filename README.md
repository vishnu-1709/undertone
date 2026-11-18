# undertone

An audio file that sounds like a normal song on a speaker, and has your voice in it on earphones.

## How it works

- Left = Cover + Voice, Right = Cover − Voice
- A speaker plays Left + Right, so the voice cancels and only the cover is left.
- Earphones keep the channels apart, so the voice is heard.

Three versions are built and compared:

| Mode | Left | Right | On earphones |
| --- | --- | --- | --- |
| `classic` | C + V | C − V | Cover in both ears, voice underneath |
| `oneear` | 2C + V | −V | Right ear hears only the voice |
| `perslice` | (1+a)C + V | 2C − L | Cover moves to the left ear only where and when the voice is |

In every mode (L + R) / 2 equals the cover exactly.

## Phase 0 lab

```bash
cd lab
pip install -r requirements.txt          # also needs ffmpeg for reencode.sh

# 1. make variants from your recording and a cover song
python make_variants.py --voice my_voice.wav --cover song.mp3 --out out
#    or try it with synthetic audio first
python make_variants.py --demo --out out

# 2. re-encode every variant the way chat apps might
./reencode.sh out

# 3. measure leak and voice level for every file
python measure.py out/*.wav out/reencoded/*.wav
```

Options for `make_variants.py`: `--modes classic oneear perslice`, `--levels -10 -6` (voice dB under the cover), `--lowpass none 1500 1000` (Hz).

### Reading `measure.py`

- **leak**: voice level left in the speaker (mono) mix. Below −40 dB is clean.
- **L voice / R voice**: voice level against everything else in each ear. Higher is clearer.
- **verdict**: `OK`, `LEAKS` (voice audible on speaker) or `VOICE LOST` (codec destroyed it).

The numbers check the file itself. A phone with two speakers can still leak a little in the air, so finish with the listening test: speaker at arm's length and held close, then earphones.

### Results with the synthetic demo

- Originals cancel to about −100 dB in the mono mix.
- MP3 320, MP3 128, AAC 256 and Opus 64 keep the voice hidden and intact in all three modes.
- Mono playback removes the voice, as expected.
- Opus 24 kbps (voice-note-grade) destroys the voice in `classic`; `oneear` survives it.
- AAC 64 makes `oneear` leak (about −30 dB).

Re-run with your own voice and cover; real speech and music will move these numbers.

## Recording tips

Speak softly in your normal voice, close to the mic. A real whisper has little energy below 1 kHz and gets filtered out.

## Test bench website (`web/`)

A single static page for trying everything in the browser, no install:

1. Record or upload your voice, or use the test voice.
2. Use the built-in rain or upload a song.
3. Pick mode, voice level and low-pass, then **Build file** (or **Build all 3 modes**).
4. For each result: 🔊 **Speaker** plays (L+R)/2 · 📱 **Two-speaker sim** mimics a phone with spaced speakers (adjust ear offset and far-speaker volume) · 🎧 **Earphones** plays stereo · **Left/Right only** · ⬇ **WAV** to send to real phones.

Metrics shown: voice level on one speaker, on the two-speaker sim, and in each ear.

Run locally: open `web/index.html` (recording needs https or localhost, e.g. `python3 -m http.server -d web`).
Deploy on Vercel: import the repo and set **Root Directory** to `web`.
