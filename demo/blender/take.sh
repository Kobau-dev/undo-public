#!/bin/zsh
# One full Blender take: replay the villa session, record the screen (no cursor, no audio, pointer logged),
# ask Undo, wait until it is done. Run from the repo root, with `python -m undo run` already running (see README).
# usage: zsh demo/blender/take.sh [N]
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$ROOT/demo/blender"
PY="$ROOT/.venv/bin/python"
B="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
LOG="${UNDO_LOG:-$DIR/out/undo.log}"
N=${1:-1}
mkdir -p "$DIR/out"
OUT="$DIR/out/take$N.mov"
[[ -f "$DIR/villa_martin.blend" ]] || "$B" -b --factory-startup --python-expr "import bpy
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
bpy.ops.wm.save_as_mainfile(filepath='$DIR/villa_martin.blend')" >/dev/null 2>&1
touch "$LOG"
pkill -f "Blender --factory-startup" ; sleep 1.5
rm -f "$DIR/out/villa.log"
VILLA_LOG="$DIR/out/villa.log" VILLA_DELAY=11 "$B" --factory-startup "$DIR/villa_martin.blend" --python "$DIR/villa_demo.py" > "$DIR/out/blender.log" 2>&1 &
sleep 6
osascript -e 'tell application "Blender" to activate'; sleep 1
"$PY" "$DIR/hover.py" 1300 820
START_LINES=$(( $(wc -l < "$LOG") + 1 ))
ffmpeg -v error -y -f avfoundation -capture_cursor 0 -capture_mouse_clicks 0 -framerate 30 -i "1:none" \
  -c:v libx264 -preset ultrafast -crf 16 -pix_fmt yuv420p "$OUT" &
FF=$!
"$PY" "$DIR/cursor_log.py" "${OUT%.mov}_cursor.jsonl" &
CL=$!
echo "REC_START $(date +%s.%N)"
for i in $(seq 60); do grep -q done "$DIR/out/villa.log" 2>/dev/null && break; sleep 1; done
sleep 3.5
osascript -e 'tell application "Blender" to activate'; sleep 0.5
"$PY" "$DIR/ask.py" || { kill -INT $FF; kill -TERM $CL; exit 1; }
for i in $(seq 150); do tail -n +$START_LINES "$LOG" | grep -q "executor finished" && break; sleep 1; done
tail -n +$START_LINES "$LOG" | grep -E "executor finished|analysis ok|step " | cut -c1-140
sleep 5
kill -INT $FF; kill -TERM $CL; wait $FF
echo "TAKE $N saved: $OUT"
