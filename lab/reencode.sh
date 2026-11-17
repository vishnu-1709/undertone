#!/usr/bin/env bash
# Re-encode every variant the way chat apps might, then decode back to WAV
# so measure.py can check whether the hidden voice survived.
#
# Usage: ./reencode.sh [input_dir] [output_dir]
set -euo pipefail

IN="${1:-out}"
OUT="${2:-$IN/reencoded}"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

enc() {  # enc <tag> <ext> <ffmpeg encode args...>
  local tag="$1" ext="$2"; shift 2
  ffmpeg -loglevel error -y -i "$SRC" "$@" "$TMP/x.$ext"
  ffmpeg -loglevel error -y -i "$TMP/x.$ext" -ar 48000 -ac 2 -c:a pcm_f32le \
    "$OUT/${BASE}__${tag}.wav"
}

for SRC in "$IN"/*.wav; do
  BASE="$(basename "$SRC" .wav)"
  echo "re-encoding $BASE"
  enc mp3-320-stereo mp3 -c:a libmp3lame -b:a 320k -joint_stereo 0
  enc mp3-128-joint  mp3 -c:a libmp3lame -b:a 128k
  enc aac-256        m4a -c:a aac -b:a 256k
  enc aac-64         m4a -c:a aac -b:a 64k
  enc opus-64        ogg -c:a libopus -b:a 64k
  enc opus-24        ogg -c:a libopus -b:a 24k
  enc mono           wav -ac 1
done
echo "done -> $OUT"
